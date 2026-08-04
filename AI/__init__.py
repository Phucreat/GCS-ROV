"""
AI Module Package for GCS ROV Control System
=============================================
Local-First (100% Offline) Dual-Task AI Agent:
  - Task 1: CV Engine (YOLOv11 Underwater Vision + Fine-Tuning)
  - Task 2: Voice Co-Pilot Agent (Silero VAD -> Faster-Whisper -> Qwen2.5 SLM / LangGraph -> Piper TTS)
  - Safety Guard: Human-in-the-Loop Validation for MAVLink Controls
"""

__version__ = "1.0.0"
