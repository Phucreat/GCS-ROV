"""
agent_brain.py - Local SLM & LangGraph Agent Orchestrator (Task 2)
====================================================================
Bộ não Agent Cục bộ (Local SLM & Agent Orchestrator):
  - Model: Qwen2.5-3B-Instruct / Qwen2.5-7B-Instruct qua Ollama (localhost:11434)
  - Framework: LangGraph StateGraph concept & Pydantic Structured Output
  - Tích hợp Safety Guard (Human-in-the-Loop Validation)
  - Tra cứu quy trình thao tác chuẩn SOP (RAG siêu nhẹ)
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from AI.safety_guard import CommandCategory, SafetyGuard


# ---------------------------------------------------------------------------
# Pydantic Structured Output Model
# ---------------------------------------------------------------------------
class AgentToolCall(BaseModel):
    action: str = Field(description="Tên hàm điều khiển (vd: set_lights, arm_thrusters, emergency_stop, read_sop, get_depth)")
    params: Dict[str, Any] = Field(default_factory=dict, description="Tham số truyền cho hàm")


class AgentOutputSchema(BaseModel):
    intent: str = Field(description="Loại ý định: 'control', 'query_telemetry', 'query_sop', 'emergency_alert', 'chat'")
    tool_call: Optional[AgentToolCall] = Field(default=None, description="Thông tin lệnh điều khiển")
    speech_response: str = Field(description="Câu trả lời bằng giọng nói tiếng Việt ngắn gọn để Piper TTS đọc")
    requires_confirmation: bool = Field(default=False, description="True nếu là lệnh nguy hiểm cần phi công xác nhận")


# ---------------------------------------------------------------------------
# Local SLM Engine via Ollama API
# ---------------------------------------------------------------------------
class LocalSLMEngine:
    """
    Connects to local Ollama server running Qwen2.5-3B-Instruct or Qwen2.5-7B-Instruct.
    Falls back to fast rule-based parser if Ollama is unreachable.
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        model_name: str = "qwen2.5:3b-instruct",
    ) -> None:
        self._url = ollama_url.rstrip("/")
        self._model = model_name
        self._available: Optional[bool] = None

    def check_availability(self) -> bool:
        """Check if local Ollama server is active."""
        try:
            req = urllib.request.Request(f"{self._url}/api/tags", headers={"User-Agent": "GCS_ROV"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    self._available = True
                    return True
        except Exception:
            pass
        self._available = False
        return False

    def generate_agent_response(
        self, prompt: str, system_context: str
    ) -> Optional[Dict[str, Any]]:
        """Call Ollama /api/generate with JSON format schema."""
        if not self.check_availability():
            return None

        system_instruction = (
            "Bạn là Trợ lý Ảo Co-Pilot cho phần mềm điều khiển robot lặn ROV (GCS ROV Assistant).\n"
            "Nhiệm vụ của bạn: Trả lời ngắn gọn, chính xác bằng tiếng Việt và xuất kết quả định dạng JSON chuẩn.\n"
            "Các hàm hỗ trợ: set_lights(intensity=0..100), arm_thrusters(), disarm_thrusters(), emergency_stop(), "
            "read_sop(id='pipeline_inspection'), get_depth(), take_snapshot().\n\n"
            f"Bối cảnh hệ thống: {system_context}\n"
            "Hãy xuất JSON theo định dạng:\n"
            '{"intent": "control", "tool_call": {"action": "set_lights", "params": {"value": 100}}, '
            '"speech_response": "Đã bật đèn rọi tối đa.", "requires_confirmation": false}'
        )

        payload = {
            "model": self._model,
            "prompt": prompt,
            "system": system_instruction,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 250},
        }

        try:
            req = urllib.request.Request(
                f"{self._url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "GCS_ROV"},
            )
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    res_text = data.get("response", "")
                    return json.loads(res_text)
        except Exception as exc:
            print(f"[LocalSLM] Ollama generate error: {exc}")
        return None


# ---------------------------------------------------------------------------
# LangGraph Concept StateGraph Orchestrator
# ---------------------------------------------------------------------------
class ROVAgentBrain:
    """
    Agent Orchestrator applying LangGraph StateGraph flow & Human-in-the-Loop Safety.
    """

    def __init__(
        self,
        sop_json_path: str = "AI/sop_rules.json",
        ollama_url: str = "http://localhost:11434",
        model_name: str = "qwen2.5:3b-instruct",
    ) -> None:
        self.safety_guard = SafetyGuard(confirmation_timeout_s=15.0)
        self.slm_engine = LocalSLMEngine(ollama_url=ollama_url, model_name=model_name)
        self.sop_rules = self._load_sop_rules(sop_json_path)

    def _load_sop_rules(self, path: str) -> List[Dict]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f).get("sop_procedures", [])
            except Exception as e:
                print(f"[AgentBrain] Error loading SOP rules: {e}")
        return []

    def process_pilot_input(
        self, text: str, telemetry_context: Dict[str, Any]
    ) -> Tuple[AgentOutputSchema, Optional[Dict]]:
        """
        Process pilot voice text input.
        Returns:
          - (AgentOutputSchema, action_to_execute_immediately_if_any)
        """
        text_clean = text.strip()

        # Step 1: Check if pilot is replying to a PENDING SAFETY CONFIRMATION
        if self.safety_guard.has_pending_confirmation():
            confirmed, msg, pending = self.safety_guard.process_pilot_voice_reply(text_clean)
            if confirmed and pending:
                output = AgentOutputSchema(
                    intent="control",
                    tool_call=AgentToolCall(action=pending["action"], params=pending.get("params", {})),
                    speech_response=msg,
                    requires_confirmation=False,
                )
                return output, pending
            else:
                output = AgentOutputSchema(
                    intent="confirmation_response",
                    tool_call=None,
                    speech_response=msg,
                    requires_confirmation=False,
                )
                return output, None

        # Step 2: Try Local SLM (Qwen2.5 via Ollama)
        ctx_str = f"Depth={telemetry_context.get('depth', 0.0)}m, Voltage={telemetry_context.get('voltage', 0.0)}V, Mode={telemetry_context.get('mode', 'MANUAL')}"
        slm_res = self.slm_engine.generate_agent_response(text_clean, ctx_str)

        if slm_res is not None:
            try:
                out = AgentOutputSchema(**slm_res)
                return self._evaluate_safety_and_build(out)
            except Exception as exc:
                print(f"[AgentBrain] Pydantic parsing error: {exc}")

        # Step 3: Fast Rule-Based Fallback (Zero-latency offline regex)
        return self._rule_based_fallback(text_clean, telemetry_context)

    def process_emergency_event(self, event_type: str, details: str) -> AgentOutputSchema:
        """Handle proactive critical alerts (e.g. LEAK_DETECTED or Diver Hazard)."""
        if event_type == "pipeline_leak":
            speech = "CẢNH BÁO KHẨN CẤP! Phát hiện RÒ RỈ ĐƯỜNG ỐNG bên dưới ROV! Hãy chuẩn bị chụp ảnh ghi lại vị trí."
        elif event_type == "diver_danger":
            speech = "CẢNH BÁO AN TOÀN! Phát hiện thợ lặn ở quá gần khu vực chân vịt! Yêu cầu giảm tốc ngay lập tức."
        else:
            speech = f"CẢNH BÁO SỰ CỐ KHẨN CẤP: {details}"

        return AgentOutputSchema(
            intent="emergency_alert",
            tool_call=None,
            speech_response=speech,
            requires_confirmation=False,
        )

    def _evaluate_safety_and_build(
        self, out: AgentOutputSchema
    ) -> Tuple[AgentOutputSchema, Optional[Dict]]:
        """Validate action with SafetyGuard."""
        if out.tool_call and out.tool_call.action:
            action_name = out.tool_call.action
            params = out.tool_call.params

            allowed, msg, pending = self.safety_guard.request_execution(action_name, params)
            if not allowed:
                out.requires_confirmation = True
                out.speech_response = msg
                return out, None
            else:
                return out, {"action": action_name, "params": params}

        return out, None

    def _rule_based_fallback(
        self, text: str, telemetry: Dict[str, Any]
    ) -> Tuple[AgentOutputSchema, Optional[Dict]]:
        """High-speed offline keyword parser for voice commands & SOP RAG."""
        text_lower = text.lower()
        depth = telemetry.get("depth", 0.0)

        # 1. Lights Command
        if "bật đèn" in text_lower or "đèn rọi" in text_lower:
            action = "set_lights"
            params = {"value": 100}
            speech = f"Đã bật đèn rọi tối đa. Độ sâu hiện tại là {depth:.1f} mét."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params=params), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # 2. Critical ARM / DISARM Command
        elif "khởi động động cơ" in text_lower or "arm động cơ" in text_lower:
            action = "arm_thrusters"
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action), speech_response="")
            return self._evaluate_safety_and_build(out)

        elif "ngắt động cơ" in text_lower or "tắt động cơ" in text_lower or "khẩn cấp" in text_lower:
            action = "emergency_stop"
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action), speech_response="")
            return self._evaluate_safety_and_build(out)

        # 3. SOP RAG Search
        elif "quy trình" in text_lower or "hướng dẫn" in text_lower or "sop" in text_lower:
            sop_text = self._search_sop(text_lower)
            out = AgentOutputSchema(intent="query_sop", tool_call=AgentToolCall(action="read_sop"), speech_response=sop_text)
            return out, None

        # 4. Telemetry Inquiry
        elif "độ sâu" in text_lower or "điện áp" in text_lower or "thông số" in text_lower:
            speech = f"Báo cáo thông số ROV: Độ sâu hiện tại {depth:.2f} mét. Điện áp tether {telemetry.get('voltage', 0.0):.1f} Volts."
            out = AgentOutputSchema(intent="query_telemetry", speech_response=speech)
            return out, None

        # 5. Default Chat Response
        speech = f"Đã nghe rõ lệnh: '{text}'. Hệ thống đang ở trạng thái hoạt động bình thường."
        out = AgentOutputSchema(intent="chat", speech_response=speech)
        return out, None

    def _search_sop(self, query: str) -> str:
        """Simple RAG over local sop_rules.json."""
        for sop in self.sop_rules:
            title = sop.get("title", "").lower()
            sop_id = sop.get("id", "").lower()
            if "ống" in query or "pipeline" in query:
                if "pipeline" in sop_id or "ống" in title:
                    steps = sop.get("steps", [])
                    return f"Quy trình kiểm tra đường ống: {steps[0]} {steps[1]}"
            elif "thợ lặn" in query or "diver" in query:
                if "diver" in sop_id:
                    steps = sop.get("steps", [])
                    return f"Quy trình an toàn thợ lặn: {steps[0]} {steps[1]}"

        # Default fallback SOP
        if self.sop_rules:
            first = self.sop_rules[0]
            return f"Quy trình chuẩn {first.get('title')}: {first.get('steps')[0]}"
        return "Hiện chưa tìm thấy tài liệu quy trình thao tác chuẩn phù hợp."
