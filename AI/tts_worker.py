"""
tts_worker.py - Piper TTS / Kokoro-TTS Offline Audio Synthesizer
==================================================================
Phát âm thanh giọng nói tiếng Việt/Anh hoàn toàn Offline với độ trễ < 50ms.
Hỗ trợ chế độ Ưu tiên Cảnh báo Khẩn cấp (Emergency Audio Override).
"""

from __future__ import annotations

import os
import queue
import subprocess
import time
from typing import Optional

try:
    from PyQt6.QtCore import QThread, pyqtSignal
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal

# Pyttsx3 / System TTS Fallback Helper
_engine = None


def _get_pyttsx3_engine():
    global _engine
    if _engine is None:
        try:
            import pyttsx3
            _engine = pyttsx3.init()
            _engine.setProperty("rate", 175)  # Slightly faster for pilot efficiency
            _engine.setProperty("volume", 1.0)
        except Exception:
            _engine = False
    return _engine if _engine is not False else None


class TTSWorker(QThread):
    """
    Background worker thread for offline Text-to-Speech audio synthesis.
    Supports Piper TTS C++ binary or pyttsx3 fallback.
    """

    sig_speech_started = pyqtSignal(str)
    sig_speech_finished = pyqtSignal()
    sig_error = pyqtSignal(str)

    def __init__(
        self,
        piper_path: str = "tools/piper/piper.exe",
        model_path: str = "models/voice_agent/vi_VN-piper.onnx",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._piper_path = piper_path
        self._model_path = model_path
        self._running = False
        self._speech_queue: queue.Queue = queue.Queue()

    def speak(self, text: str, is_emergency: bool = False) -> None:
        """Queue text to be spoken. Emergency audio clears the queue instantly."""
        if not text.strip():
            return
        if is_emergency:
            # Clear pending queue for immediate emergency announcement
            while not self._speech_queue.empty():
                try:
                    self._speech_queue.get_nowait()
                except queue.Empty:
                    break

        self._speech_queue.put((text.strip(), is_emergency))

    def stop(self) -> None:
        self._running = False
        if not self.wait(1500):
            self.terminate()
            self.wait()

    def run(self) -> None:
        self._running = True
        print("[TTSWorker] Text-to-Speech audio synthesizer started.")

        while self._running:
            try:
                try:
                    text, is_emergency = self._speech_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                self.sig_speech_started.emit(text)
                self._synthesize_and_play(text, is_emergency)
                self.sig_speech_finished.emit()

            except Exception as exc:
                print(f"[TTSWorker] Error in TTS synthesis: {exc}")

    def _synthesize_and_play(self, text: str, is_emergency: bool) -> None:
        """Synthesize text using Piper TTS or pyttsx3 fallback."""
        # Method 1: Piper TTS C++ Engine (Low latency < 50ms)
        if os.path.exists(self._piper_path) and os.path.exists(self._model_path):
            try:
                out_wav = "scratch/temp_tts.wav"
                cmd = [
                    self._piper_path,
                    "--model", self._model_path,
                    "--output_file", out_wav,
                ]
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                proc.communicate(input=text.encode("utf-8"))

                if os.path.exists(out_wav):
                    self._play_wav_file(out_wav)
                    return
            except Exception as e:
                print(f"[TTSWorker] Piper TTS error ({e}), falling back to Pyttsx3...")

        # Method 2: Pyttsx3 / System SAPI5 Fallback
        engine = _get_pyttsx3_engine()
        if engine is not None:
            try:
                print(f"[TTSWorker] Speaking: '{text}'")
                engine.say(text)
                engine.runAndWait()
            except Exception as exc:
                print(f"[TTSWorker] Pyttsx3 speech error: {exc}")
        else:
            print(f"[TTSWorker] (Silent Mode) Audio Output: '{text}'")

    def _play_wav_file(self, wav_path: str) -> None:
        """Play WAV audio via winsound or sounddevice."""
        try:
            import winsound
            winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            pass
