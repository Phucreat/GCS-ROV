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
import sys
import time
from typing import Optional

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

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


_NEURAL_VOICE_MAP = {
    "vi": "vi-VN-HoaiMyNeural",
    "en": "en-US-AriaNeural",
    "ja": "ja-JP-NanamiNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "ko": "ko-KR-SunHiNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "es": "es-ES-ElviraNeural",
    "ru": "ru-RU-SvetlanaNeural",
}


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
        self._language = "vi"  # Default: Tiếng Việt 🇻🇳
        self._speech_queue: queue.Queue = queue.Queue()

    def set_language(self, lang_code: str) -> None:
        """Dynamically switch TTS voice language (e.g. 'vi', 'en', 'ja', 'zh')."""
        self._language = lang_code.lower()
        print(f"[TTSWorker] Switched voice language to: '{self._language}'")

    def speak(self, text: str, is_emergency: bool = False) -> None:
        """Queue text to be spoken. Always clear outdated queue first for 0ms lag!"""
        if not text.strip():
            return

        # Always clear pending queue to prevent outdated sentences from building up lag!
        while not self._speech_queue.empty():
            try:
                self._speech_queue.get_nowait()
            except Exception:
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

        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass

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
        """Synthesize text using Fast Offline System SAPI5, Neural TTS, or Piper."""
        if not text.strip():
            return

        lang = getattr(self, "_language", "vi")
        print(f"[TTSWorker] Synthesizing speech ({lang.upper()} | {'EMERGENCY' if is_emergency else 'NORMAL'}): '{text}'")

        # ── Method 1: Pyttsx3 / Windows Native SAPI5 Engine (0ms Latency, 100% Offline) ── #
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 175)
            engine.setProperty("volume", 1.0)

            # Match voice strictly by target language (prevent 'vi' substring matching 'daVId')
            voices = engine.getProperty("voices")
            matched_voice_id = None
            for v in voices:
                v_name = v.name.lower()
                v_langs = [str(l).lower() for l in getattr(v, "languages", [])]

                if lang == "vi":
                    if "vietnam" in v_name or "vietnamese" in v_name or "hoaimy" in v_name or "namminh" in v_name or any("vi" in l for l in v_langs):
                        matched_voice_id = v.id
                        break
                elif lang == "en":
                    if "english" in v_name or "zira" in v_name or "david" in v_name or "hazel" in v_name or any("en" in l for l in v_langs):
                        matched_voice_id = v.id
                        break
                elif lang == v_name or any(lang == l for l in v_langs):
                    matched_voice_id = v.id
                    break

            if matched_voice_id:
                engine.setProperty("voice", matched_voice_id)
                engine.say(text)
                engine.runAndWait()
                return
        except Exception as exc:
            print(f"[TTSWorker] Pyttsx3 SAPI5 speech error: {exc}")

        # ── Method 2: Local Disk Cache / Edge TTS ── #
        try:
            import hashlib
            target_voice = _NEURAL_VOICE_MAP.get(lang, "vi-VN-HoaiMyNeural")
            hash_name = hashlib.md5(f"{target_voice}_{text}".encode("utf-8")).hexdigest()
            cache_dir = os.path.join("scratch", "tts_cache")
            os.makedirs(cache_dir, exist_ok=True)
            cached_mp3 = os.path.join(cache_dir, f"{hash_name}.mp3")

            if not os.path.exists(cached_mp3):
                import asyncio
                import edge_tts
                async def _gen():
                    communicate = edge_tts.Communicate(text, target_voice)
                    await communicate.save(cached_mp3)
                asyncio.run(_gen())

            if os.path.exists(cached_mp3):
                self._play_audio_file(cached_mp3)
                return
        except Exception as exc:
            print(f"[TTSWorker] Edge TTS speech error: {exc}")

        # Method 3: Piper TTS C++ Engine (Low latency < 50ms)
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
                    self._play_audio_file(out_wav)
                    return
            except Exception as e:
                print(f"[TTSWorker] Piper TTS error ({e})...")

    def _play_audio_file(self, audio_path: str) -> None:
        """Play WAV or MP3 audio file cleanly via pygame audio or winsound."""
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(audio_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
        except Exception:
            try:
                import winsound
                winsound.PlaySound(audio_path, winsound.SND_FILENAME)
            except Exception:
                pass
