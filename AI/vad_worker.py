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
        threshold: float = 0.5,
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

        # Attempt sounddevice / pyaudio mic stream
        audio_stream = None
        try:
            import sounddevice as sd

            def audio_callback(indata, frames, time_info, status):
                if not self._running:
                    return
                pcm_data = indata[:, 0].astype(np.float32)
                self._process_audio_chunk(pcm_data)

            audio_stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="float32",
                blocksize=int(self._sample_rate * 0.03), # 30ms block
                callback=audio_callback,
            )
            audio_stream.start()

            while self._running:
                time.sleep(0.1)

            audio_stream.stop()
            audio_stream.close()

        except Exception as exc:
            print(f"[VADWorker] Microphone stream unavailable ({exc}). VAD running in passive mode.")
            while self._running:
                time.sleep(0.5)

    def _process_audio_chunk(self, chunk: np.ndarray) -> None:
        """Process 30ms audio chunk with Silero VAD or energy fallback."""
        model = _get_silero_vad()
        speech_prob = 0.0

        if model is not None:
            try:
                import torch
                tensor_chunk = torch.from_numpy(chunk)
                speech_prob = model(tensor_chunk, self._sample_rate).item()
            except Exception:
                speech_prob = float(np.sqrt(np.mean(chunk**2)) > 0.02)
        else:
            # Energy fallback
            energy = float(np.sqrt(np.mean(chunk**2)))
            speech_prob = 0.9 if energy > 0.03 else 0.0

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
