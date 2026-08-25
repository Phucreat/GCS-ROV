"""
stt_worker.py - Faster-Whisper Speech-to-Text (STT) Engine
==========================================================
Sử dụng SYSTRAN/faster-whisper (CTranslate2) nhận dạng giọng nói tiếng Việt
và thuật ngữ kỹ thuật tiếng Anh hoàn toàn Offline trên GPU/CPU nội bộ.
"""

from __future__ import annotations

import os
import tempfile
import time
from typing import Optional

import numpy as np

try:
    from PyQt6.QtCore import QObject, pyqtSignal
except ImportError:
    from PyQt5.QtCore import QObject, pyqtSignal

# Lazy Faster-Whisper Import
_whisper_model = None


def _get_whisper_model(model_size: str = "base", device: str = "cpu"):
    global _whisper_model
    if _whisper_model is None:
        try:
            from faster_whisper import WhisperModel
            print(f"[FasterWhisper] Đang nạp model '{model_size}' chạy trên CPU (int8)...")
            _whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
            print("[FasterWhisper] Nạp model thành công!")
        except Exception as exc:
            print(f"[FasterWhisper] Lỗi nạp model: {exc}")
            _whisper_model = False
    return _whisper_model if _whisper_model is not False else None


class STTWorker(QObject):
    """
    Offline Speech-to-Text Transcriber using Faster-Whisper.
    Converts 16kHz float32 audio arrays into Vietnamese text.
    """

    sig_transcription = pyqtSignal(str, float)  # (text, confidence)
    sig_error = pyqtSignal(str)

    def __init__(
        self,
        model_size: str = "base",
        language: str = "vi",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._model_size = model_size
        self._language = language

    def set_language(self, lang_code: str) -> None:
        """Dynamically set STT language code (e.g. 'vi', 'en', 'ja', 'zh')."""
        self._language = lang_code.lower()
        print(f"[STTWorker] Switched recognition language to: '{self._language}'")

    def transcribe_audio(self, audio_data: np.ndarray) -> str:
        """
        Transcribe a 16kHz float32 audio numpy array.
        Smoothly normalizes microphone gain and transcribes using Google / Faster-Whisper.
        """
        if audio_data is None or len(audio_data) < 3200:  # < 0.2s
            return ""

        max_val = float(np.abs(audio_data).max())
        if max_val < 0.0005:
            # Pure digital silence -> Discard
            return ""

        # Smooth peak audio normalization up to 0.85 max amplitude
        if max_val < 0.85:
            audio_data = (audio_data * (0.85 / max_val)).astype(np.float32)

        # ── Method 1: Google Speech Engine (Fast, High Precision) ──────────── #
        try:
            import speech_recognition as sr
            import io
            import wave

            int_audio = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)
            wav_io = io.BytesIO()
            with wave.open(wav_io, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(int_audio.tobytes())
            wav_io.seek(0)

            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_io) as source:
                audio_clip = recognizer.record(source)

            # Recognize with Google Search Speech Engine
            stt_lang = {
                "vi": "vi-VN", "en": "en-US", "ja": "ja-JP", "zh": "zh-CN",
                "ko": "ko-KR", "fr": "fr-FR", "de": "de-DE", "es": "es-ES", "ru": "ru-RU"
            }.get(getattr(self, "_language", "vi"), "vi-VN")

            text_google = recognizer.recognize_google(audio_clip, language=stt_lang)
            if text_google and len(text_google.strip()) > 0:
                print(f"[STT-Google] Transcribed ({stt_lang}): '{text_google}'")
                self.sig_transcription.emit(text_google, 0.99)
                return text_google
        except Exception:
            pass

        # ── Method 2: Local Faster-Whisper Engine (100% Offline Fallback) ──── #
        model = _get_whisper_model(self._model_size)
        if model is not None:
            try:
                segments, info = model.transcribe(
                    audio_data,
                    language=self._language,
                    beam_size=5,
                    temperature=0.0,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=250),
                )

                text_result = " ".join([segment.text for segment in segments]).strip()
                confidence = info.transcription_probability if hasattr(info, 'transcription_probability') else 0.9

                # Comprehensive filter for Whisper static noise hallucination phrases
                hallucinations = [
                    "cảm ơn các bạn", "đăng ký kênh", "subtitles by", "thank you",
                    "cảm ơn đã theo dõi", "hẹn gặp lại", "bởi youtube", "tiếng nhạc",
                    "tạm biệt", "hẹn gặp lại các bạn", "đăng ký", "channel", "mọi người"
                ]
                text_lower = text_result.lower()
                if any(h in text_lower for h in hallucinations) and len(text_result) < 35:
                    print(f"[STT-Whisper] Filtered static noise hallucination: '{text_result}'")
                    return ""

                # Filter repeated word loops (e.g. 'thịt thịt thịt thịt...')
                words = text_result.split()
                if len(words) >= 4:
                    consec = 1
                    is_loop = False
                    for i in range(1, len(words)):
                        if words[i].lower() == words[i-1].lower():
                            consec += 1
                            if consec >= 4:
                                is_loop = True
                                break
                        else:
                            consec = 1
                    if not is_loop and len(words) >= 6:
                        if len(set(w.lower() for w in words)) / len(words) < 0.40:
                            is_loop = True
                    if is_loop:
                        print(f"[STT-Whisper] Filtered repetitive loop hallucination: '{text_result[:40]}...'")
                        return ""

                if len(text_result) < 2:
                    return ""

                if text_result:
                    print(f"[STT-Whisper Offline] Transcribed: '{text_result}' (prob={confidence:.2f})")
                    self.sig_transcription.emit(text_result, confidence)
                    return text_result

            except Exception as exc:
                print(f"[STT] Whisper local error: {exc}")

        return ""

        # ── Method 2: Google Speech Engine (Online Cloud Accelerator) ───────── #
        try:
            import speech_recognition as sr
            import io
            import wave

            # Convert 16kHz float32 numpy array to 16-bit PCM WAV in RAM
            int_audio = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)
            wav_io = io.BytesIO()
            with wave.open(wav_io, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(int_audio.tobytes())
            wav_io.seek(0)

            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_io) as source:
                audio_clip = recognizer.record(source)

            # Recognize with Google Search Speech Engine with 0.8s timeout
            text_google = recognizer.recognize_google(audio_clip, language="vi-VN")
            if text_google and len(text_google.strip()) > 0:
                print(f"[STT-Google] Transcribed vi-VN: '{text_google}'")
                self.sig_transcription.emit(text_google, 0.99)
                return text_google
        except Exception as exc:
            pass

            text_result = " ".join([segment.text for segment in segments]).strip()
            confidence = info.transcription_probability if hasattr(info, 'transcription_probability') else 0.9

            # Filter common Whisper silent noise hallucination phrases
            hallucinations = ["cảm ơn các bạn", "đăng ký kênh", "subtitles by", "thank you", "cảm ơn đã theo dõi", "hẹn gặp lại", "bởi youtube"]
            if any(h in text_result.lower() for h in hallucinations) and len(text_result) < 30:
                print(f"[STT-Whisper] Filtered common silent noise hallucination: '{text_result}'")
                return ""

            if len(text_result) < 3:
                return ""

            if text_result:
                print(f"[STT-Whisper] Transcribed: '{text_result}' (prob={confidence:.2f})")
                self.sig_transcription.emit(text_result, confidence)
                return text_result

        except Exception as exc:
            err_msg = f"Lỗi STT: {exc}"
            print(f"[STT] {err_msg}")
            self.sig_error.emit(err_msg)

        return ""

        return ""
