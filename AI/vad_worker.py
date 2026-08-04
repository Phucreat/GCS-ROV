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
        try:
            import torch
            model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                onnx=False,
            )
            _silero_model = model
            print("[SileroVAD] Loaded Silero VAD model successfully.")
        except Exception as exc:
            print(f"[SileroVAD] Warning: Torch hub load fallback to energy VAD: {exc}")
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
        # Attempt sounddevice mic stream with native sample rate + auto-resampling
        try:
            import sounddevice as sd

            try:
                dev_info = sd.query_devices(kind="input")
                native_sr = int(dev_info.get("default_samplerate", 44100))
            except Exception:
                native_sr = 44100

            def audio_callback(indata, frames, time_info, status):
                if not self._running:
                    return
                pcm_raw = indata[:, 0].astype(np.float32)
                if native_sr != 16000 and len(pcm_raw) > 0:
                    target_len = int(len(pcm_raw) * 16000 / native_sr)
                    if target_len > 0:
                        pcm_16k = np.interp(
                            np.linspace(0, len(pcm_raw) - 1, target_len),
                            np.arange(len(pcm_raw)),
                            pcm_raw,
                        ).astype(np.float32)
                    else:
                        pcm_16k = pcm_raw
                else:
                    pcm_16k = pcm_raw

                self._process_audio_chunk(pcm_16k)

            audio_stream = sd.InputStream(
                samplerate=native_sr,
                channels=1,
                dtype="float32",
                blocksize=int(native_sr * 0.03), # 30ms block
                callback=audio_callback,
            )
            audio_stream.start()

            while self._running:
                time.sleep(0.1)

            audio_stream.stop()
            audio_stream.close()

        except Exception as exc:
            print(f"[VADWorker] SoundDevice stream error: {exc}. Trying PyAudio fallback...")
            try:
                import pyaudio
                p = pyaudio.PyAudio()
                stream = p.open(
                    format=pyaudio.paFloat32,
                    channels=1,
                    rate=16000,
                    input=True,
                    frames_per_buffer=480,
                )
                while self._running:
                    data = stream.read(480, exception_on_overflow=False)
                    pcm = np.frombuffer(data, dtype=np.float32)
                    self._process_audio_chunk(pcm)
                stream.stop_stream()
                stream.close()
                p.terminate()
            except Exception as e:
                print(f"[VADWorker] PyAudio fallback error: {e}. VAD running in passive mode.")
                while self._running:
                    time.sleep(0.5)

    def _process_audio_chunk(self, chunk: np.ndarray) -> None:
        """Process 30ms audio chunk with dynamic noise floor tracking VAD."""
        if chunk is None or len(chunk) == 0:
            return

        energy = float(np.sqrt(np.mean(chunk**2)))

        # Dynamic Noise Floor Tracking (Exponential Moving Average)
        if not hasattr(self, "_noise_floor") or self._noise_floor is None:
            self._noise_floor = 0.000015

        if energy < self._noise_floor * 3.0 and energy > 0:
            self._noise_floor = 0.95 * self._noise_floor + 0.05 * energy

        model = _get_silero_vad()
        speech_prob = 0.0

        if model is not None:
            try:
                import torch
                tensor_chunk = torch.from_numpy(chunk)
                speech_prob = model(tensor_chunk, self._sample_rate).item()
            except Exception:
                speech_prob = 0.9 if energy > (self._noise_floor * 2.5) and energy > 0.00003 else 0.0
        else:
            # Dynamic energy threshold fallback: 2.5x above ambient noise floor or > 0.00003
            speech_prob = 0.9 if energy > (self._noise_floor * 2.5) and energy > 0.00003 else 0.0

        self.sig_vad_status.emit(speech_prob >= self._threshold, speech_prob)

        if speech_prob >= self._threshold:
            if not self._is_speaking:
                self._is_speaking = True
                self.sig_speech_start.emit()
                self._audio_buffer = []

            self._audio_buffer.append(chunk)
            self._silence_frames = 0
        else:
            if self._is_speaking:
                self._audio_buffer.append(chunk)
                self._silence_frames += 1

                if self._silence_frames >= self._max_silence_frames:
                    # End of speech detected
                    self._is_speaking = False
                    if len(self._audio_buffer) > 0:
                        full_audio = np.concatenate(self._audio_buffer)
                        self.sig_speech_end.emit(full_audio)
                    self._audio_buffer = []
                    self._silence_frames = 0
