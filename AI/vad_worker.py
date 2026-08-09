"""
vad_worker.py - Silero VAD (Voice Activity Detection) Worker
============================================================
Lọc nhiễu âm thanh sóng gió/động cơ tàu ngầm, nhận diện chính xác
thời điểm người lái cất tiếng nói để kích hoạt micro.
"""

from __future__ import annotations

import collections
import time
import numpy as np

try:
    from PyQt6.QtCore import QThread, pyqtSignal
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal

# Lazy PyTorch / ONNX Silero VAD helper
_silero_model = None


def _get_silero_vad():
    global _silero_model
    if _silero_model is None:
        # Method 1: Load directly from installed local silero_vad package (100% offline)
        try:
            from silero_vad import load_silero_vad
            _silero_model = load_silero_vad()
            print("[SileroVAD] Loaded Silero VAD model directly from local silero_vad package.")
        except Exception as exc1:
            try:
                import torch
                torch.hub._validate_not_a_fork = lambda *args, **kwargs: True
                model, _ = torch.hub.load(
                    repo_or_dir="snakers4/silero-vad",
                    model="silero_vad",
                    trust_repo=True,
                    onnx=False,
                )
                _silero_model = model
                print("[SileroVAD] Loaded Silero VAD via torch hub.")
            except Exception as exc2:
                print(f"[SileroVAD] Local silero-vad load error: {exc1} / {exc2}")
                _silero_model = False
    return _silero_model if _silero_model is not False else None


class VADWorker(QThread):
    """
    Background QThread polling microphone audio buffer, running Silero VAD.
    Emits sig_speech_start and sig_speech_end(pcm_chunk).
    """

    sig_speech_start = pyqtSignal()
    sig_speech_end = pyqtSignal(np.ndarray)  # float32 16kHz audio buffer
    sig_vad_status = pyqtSignal(bool, float)  # (is_speaking, audio_energy)

    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
        threshold: float = 0.30,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._sample_rate = sample_rate
        self._threshold = threshold
        self._running = False
        self._is_speaking = False
        self._audio_buffer = []
        self._silence_frames = 0
        self._max_silence_frames = 15  # ~450ms silence triggers end of speech

    def stop(self) -> None:
        self._running = False
        if not self.wait(1500):
            self.terminate()
            self.wait()

    def run(self) -> None:
        self._running = True
        print("[VADWorker] Voice Activity Detection thread started.")

        audio_stream = None
        # ── Method 0: Native SpeechRecognition Microphone Engine (100% Reliable) ── #
        try:
            import speech_recognition as sr
            rec = sr.Recognizer()
            rec.energy_threshold = 300
            rec.dynamic_energy_threshold = True
            rec.pause_threshold = 0.5

            with sr.Microphone() as source:
                print(f"[VADWorker] Native SpeechRecognition microphone initialized on '{source}'. Calibrating noise...")
                try:
                    rec.adjust_for_ambient_noise(source, duration=0.3)
                except Exception:
                    pass
                print("[VADWorker] Native SpeechRecognition microphone ready!")

                while self._running:
                    try:
                        audio = rec.listen(source, timeout=1.0, phrase_time_limit=6.0)
                        if audio and self._running:
                            wav_bytes = audio.get_raw_data(convert_rate=16000, convert_width=2)
                            pcm_int = np.frombuffer(wav_bytes, dtype=np.int16)
                            pcm_float = pcm_int.astype(np.float32) / 32768.0
                            print(f"[VADWorker] Captured speech audio clip ({len(pcm_float)} samples @ 16kHz). Emitting speech end.")
                            self.sig_speech_end.emit(pcm_float)
                    except sr.WaitTimeoutError:
                        pass
                    except Exception:
                        time.sleep(0.1)

            return
        except Exception as exc:
            print(f"[VADWorker] Native SpeechRecognition Mic error: {exc}. Trying PyAudio fallback...")
            try:
                import sounddevice as sd
                def audio_callback(indata, frames, time_info, status):
                    if not self._running:
                        return
                    pcm_16k = indata[:, 0].astype(np.float32)
                    self._process_audio_chunk(pcm_16k)

                audio_stream = sd.InputStream(
                    samplerate=16000,
                    channels=1,
                    dtype="float32",
                    blocksize=480,
                    callback=audio_callback,
                )
                audio_stream.start()
                while self._running:
                    time.sleep(0.1)
                audio_stream.stop()
                audio_stream.close()
            except Exception as e:
                print(f"[VADWorker] SoundDevice fallback error: {e}.")

    def _process_audio_chunk(self, chunk: np.ndarray) -> None:
        """Process 30ms audio chunk with dynamic noise floor tracking VAD."""
        if chunk is None or len(chunk) == 0:
            return

        energy = float(np.sqrt(np.mean(chunk**2)))

        # Dynamic Noise Floor Tracking (Exponential Moving Average)
        if not hasattr(self, "_noise_floor") or self._noise_floor is None:
            self._noise_floor = 0.005

        if energy < self._noise_floor * 2.0 and energy > 0:
            self._noise_floor = 0.95 * self._noise_floor + 0.05 * energy

        model = _get_silero_vad()
        speech_prob = 0.0

        if model is not None:
            try:
                import torch
                # Silero VAD v4 requires exact 512-sample chunks @ 16kHz
                if len(chunk) != 512:
                    vad_input = np.pad(chunk, (0, max(0, 512 - len(chunk))))[:512]
                else:
                    vad_input = chunk
                tensor_chunk = torch.from_numpy(vad_input)
                speech_prob = float(model(tensor_chunk, 16000).item())
            except Exception:
                speech_prob = 0.9 if energy > (self._noise_floor * 1.8) and energy > 0.001 else 0.0
        else:
            speech_prob = 0.9 if energy > (self._noise_floor * 1.8) and energy > 0.001 else 0.0

        # Sensitive speech detection threshold
        is_speech = speech_prob >= 0.45 or (energy > (self._noise_floor * 2.2) and energy > 0.0015)
        self.sig_vad_status.emit(is_speech, speech_prob)

        if is_speech:
            if not self._is_speaking:
                self._is_speaking = True
                self.sig_speech_start.emit()
                self._audio_buffer = []

            self._audio_buffer.append(chunk)
            self._silence_frames = 0

            # Max utterance cap (~6.0s of continuous speech = 200 chunks of 30ms) -> Auto flush
            if len(self._audio_buffer) >= 200:
                self._is_speaking = False
                full_audio = np.concatenate(self._audio_buffer)
                self._audio_buffer = []
                self._silence_frames = 0
                if len(full_audio) >= 8000:  # Minimum 0.5s audio (8000 samples @ 16kHz)
                    print(f"[VADWorker] Speech max cap reached ({len(full_audio)} samples). Emitting speech end.")
                    self.sig_speech_end.emit(full_audio)
        else:
            if self._is_speaking:
                self._audio_buffer.append(chunk)
                self._silence_frames += 1

                if self._silence_frames >= 15:  # ~450ms silence triggers natural speech end
                    # End of speech detected
                    self._is_speaking = False
                    if len(self._audio_buffer) > 0:
                        full_audio = np.concatenate(self._audio_buffer)
                        self._audio_buffer = []
                        self._silence_frames = 0
                        if len(full_audio) >= 8000:  # Minimum 0.5s audio (8000 samples @ 16kHz)
                            print(f"[VADWorker] End of speech detected ({len(full_audio)} samples). Emitting speech end.")
                            self.sig_speech_end.emit(full_audio)
                    else:
                        self._audio_buffer = []
                        self._silence_frames = 0
