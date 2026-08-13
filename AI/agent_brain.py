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
    action: Optional[str] = Field(default="read_sop", description="Tên hàm điều khiển (vd: set_lights, arm_thrusters, emergency_stop, read_sop, take_snapshot)")
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
        if self._available is not None:
            return self._available
        try:
            req = urllib.request.Request(f"{self._url}/api/tags", headers={"User-Agent": "GCS_ROV"})
            with urllib.request.urlopen(req, timeout=0.3) as resp:
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
            "Bạn là VIC - Trợ lý ảo AI chuyên nghiệp đồng hành cùng người vận hành Robot lặn ngầm CNX VIC trên Trạm điều khiển mặt đất (GCS).\n\n"
            f"TRẠNG THÁI VIỄN TRẮC THỜI GIAN THỰC (REAL-TIME TELEMETRY):\n{system_context}\n\n"
            "QUY TẮC PHẢN HỒI NGUYÊN TẮC:\n"
            "1. NĂNG LỰC TRẢ LỜI: Trả lời ngắn gọn (1 - 3 câu), súc tích, tự nhiên để đọc ra loa qua Text-to-Speech (TTS).\n"
            "2. TÂM SỰ & TRÒ CHUYỆN (Nhiệm vụ 1): Thân thiện, hóm hỉnh, khích lệ tinh thần người lái khi lặn biển. KHÔNG gọi bất kỳ Tool nào khi người dùng chỉ trò chuyện phiếm ('bạn tên gì', 'sóng to quá', 'mệt quá', 'lặn sợ quá').\n"
            "3. ĐIỀU KHIỂN PHẦN CỨNG & Ý ĐỊNH NGẦM (Nhiệm vụ 2): Nhận biết cả lệnh trực tiếp ('Bật đèn 80%') lẫn ý định ngầm ('Tối quá' -> set_lights 100, 'Lặn sâu hơn chút' -> depth control). Gọi đúng Tool tương ứng (set_lights, arm_thrusters, disarm_thrusters, emergency_stop, take_snapshot). Với các lệnh nguy hiểm (ARM, DISARM, Ngắt khẩn cấp), yêu cầu xác nhận trước.\n"
            "4. TRUY XUẤT THÔNG SỐ & CẢNH BÁO (Nhiệm vụ 3): Trả lời ngay các câu hỏi viễn trắc ('Đang lặn sâu bao nhiêu?', 'Pin còn bao nhiêu?', 'Nhiệt độ cabin sao rồi?') từ thông số viễn trắc thời gian thực ở trên. Nếu rò rỉ nước hoặc pin thấp, đưa ra cảnh báo an toàn.\n"
            "5. HƯỚNG DẪN QUY TRÌNH & GCS (Nhiệm vụ 4): Sử dụng Tool read_sop(topic=...) khi người dùng hỏi quy trình kiểm tra SOP hoặc cách dùng giao diện GCS.\n\n"
            "ĐỊNH DẠNG JSON BẮT BUỘC:\n"
            '{"intent": "chat", "tool_call": null, "speech_response": "Sóng gió trên mặt nước không làm khó được CNX VIC đâu! Tớ vẫn đang giám sát độ sâu 12.4m rất ổn định, bạn cứ yên tâm giữ vững tay lái nhé!", "requires_confirmation": false}\n'
            '{"intent": "control", "tool_call": {"action": "set_lights", "params": {"value": 100}}, "speech_response": "Tớ đã tăng đèn rọi Subsea lên 100% độ sáng cho bạn quan sát rõ hơn rồi nhé.", "requires_confirmation": false}'
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
            with urllib.request.urlopen(req, timeout=12.0) as resp:
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

    WAKE_WORD_ALIASES = ["hey vic", "vic ơi", "trợ lý vic", "cnx vic", "vic", "hey aero", "aero ơi", "aero"]

    def extract_wake_word(self, text: str) -> Tuple[bool, str]:
        """
        Check if text contains Wake Word ("Hey VIC", "VIC ơi", "CNX VIC").
        Returns (has_wake_word, clean_command_without_wake_word).
        """
        text_clean = text.strip()
        text_lower = text_clean.lower()
        has_wake = False
        command = text_clean

        for wake in self.WAKE_WORD_ALIASES:
            if wake in text_lower:
                has_wake = True
                import re
                pattern = re.compile(re.escape(wake), re.IGNORECASE)
                command = pattern.sub("", command).strip(" ,.!?:;-")
                break

        return has_wake, command

    def process_pilot_input(
        self, text: str, telemetry_context: Dict[str, Any], is_ptt: bool = False
    ) -> Tuple[Optional[AgentOutputSchema], Optional[Dict]]:
        """
        Process pilot voice text input.
        Enforces Wake Word requirement when in continuous background mode (is_ptt=False).
        """
        text_clean = text.strip()
        if not text_clean:
            return None, None

        has_wake, command_text = self.extract_wake_word(text_clean)

        if not is_ptt:
            if not has_wake:
                # Discard background TV noise ("xôi lạc TV", "được", "à", "ừ") silently!
                return None, None
            if not command_text:
                # User just called the assistant name ("Hey VIC" / "VIC ơi")
                speech = "CNX VIC nghe đây! Bạn cần hỗ trợ gì?"
                out = AgentOutputSchema(intent="chat", speech_response=speech)
                return out, None
            text_clean = command_text
        else:
            if command_text:
                text_clean = command_text

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

        # Step 2: High-Precision Deterministic Hardware & Telemetry Engine (0ms Latency Priority)
        text_lower = text_clean.lower()
        is_hardware_or_telemetry = any(k in text_lower for k in [
            "đèn", "bật", "tắt", "rọi", "arm", "disarm", "động cơ", "ngắt", "khẩn cấp",
            "độ sâu", "điện áp", "pin", "dung lượng", "nhiệt độ", "thông số", "cảm biến",
            "quy trình", "hướng dẫn", "sop", "chụp ảnh", "lưu ảnh", "snapshot"
        ])

        if is_hardware_or_telemetry:
            return self._rule_based_fallback(text_clean, telemetry_context)

        # Step 3: Local SLM (Qwen2.5 via Ollama) for Casual Chat & Morale Support
        ctx_str = f"Depth={telemetry_context.get('depth', 0.0)}m, Voltage={telemetry_context.get('voltage', 0.0)}V, Mode={telemetry_context.get('mode', 'MANUAL')}"
        slm_res = self.slm_engine.generate_agent_response(text_clean, ctx_str)

        if slm_res is not None:
            try:
                out = AgentOutputSchema(**slm_res)
                if out.tool_call and out.tool_call.action == "read_sop":
                    topic = str(out.tool_call.params.get("topic", text_clean))
                    sop_text = self._search_sop(topic if topic != text_clean else text_clean)
                    if sop_text:
                        out.speech_response = sop_text
                return self._evaluate_safety_and_build(out)
            except Exception as exc:
                print(f"[AgentBrain] Pydantic parsing error: {exc}")

        # Fallback to rule engine if Ollama is offline or unparseable
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
        # Phonetic Vietnamese Normalization for noisy speech recognition
        text_lower = (
            text.lower()
            .replace("bậc", "bật").replace("đền", "đèn").replace("đen", "đèn")
            .replace("tắc", "tắt").replace("gát", "ngắt").replace("gắt", "ngắt")
        )
        depth = telemetry.get("depth", 0.0)

        # 0. Agent Identity & Friendly Morale Chat (Nhiệm vụ 1: Tâm sự & Trò chuyện)
        if any(k in text_lower for k in ["tên gì", "tên là gì", "bạn là ai", "ai đây", "who are you", "giới thiệu"]):
            speech = "Tôi là CNX VIC, trợ lý ảo AI chuyên nghiệp hỗ trợ vận hành robot lặn ngầm."
            out = AgentOutputSchema(intent="chat", speech_response=speech)
            return out, None

        elif any(k in text_lower for k in ["sóng to", "rợn tóc gáy", "sợ quá", "biển xấu"]):
            speech = f"Sóng lớn không làm khó được CNX VIC đâu! Hệ thống đang giữ độ sâu {depth:.1f}m rất ổn định."
            out = AgentOutputSchema(intent="chat", speech_response=speech)
            return out, None

        elif any(k in text_lower for k in ["mệt quá", "căng thẳng", "đuối quá"]):
            speech = "Bạn nghỉ tay một chút nhé, CNX VIC đang giám sát toàn bộ hệ thống."
            out = AgentOutputSchema(intent="chat", speech_response=speech)
            return out, None

        # 1. Ý Định Ngầm & Điều Khiển Trực Tiếp (Nhiệm vụ 2)
        # Ý định ngầm: "Tối quá", "Không thấy gì", "Tối thui" -> Tăng đèn rọi 100%
        if any(k in text_lower for k in ["tối quá", "tối thui", "không nhìn thấy", "chẳng nhìn rõ", "tối"]):
            action = "set_lights"
            speech = "Đã tăng đèn rọi Subsea lên 100% độ sáng."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"value": 100}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # Chụp ảnh / Lưu khung hình
        elif any(k in text_lower for k in ["chụp ảnh", "chụp hình", "lưu ảnh", "snapshot"]):
            action = "take_snapshot"
            speech = "Đã chụp và lưu ảnh vào thư mục media thành công."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # 2. SOP RAG Search (Nhiệm vụ 4: Quy trình & Hướng dẫn GCS)
        elif "quy trình" in text_lower or "hướng dẫn" in text_lower or "sop" in text_lower or "cách dùng" in text_lower:
            sop_text = self._search_sop(text_lower)
            out = AgentOutputSchema(intent="query_sop", tool_call=AgentToolCall(action="read_sop"), speech_response=sop_text)
            return out, None

        # 3. Critical ARM / DISARM / Emergency Command
        elif "khởi động động cơ" in text_lower or "arm động cơ" in text_lower:
            action = "arm_thrusters"
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action), speech_response="")
            return self._evaluate_safety_and_build(out)

        elif "ngắt động cơ" in text_lower or "tắt động cơ" in text_lower or "khẩn cấp" in text_lower:
            action = "emergency_stop"
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action), speech_response="")
            return self._evaluate_safety_and_build(out)

        # Lệnh Đèn Rọi Trực Tiếp
        elif "bật đèn" in text_lower or "tắt đèn" in text_lower or "đèn rọi" in text_lower or "đèn" in text_lower:
            action = "set_lights"
            val = 0 if "tắt" in text_lower else 100
            import re
            nums = re.findall(r"\d+", text_lower)
            if nums and "tắt" not in text_lower:
                try:
                    val = max(0, min(100, int(nums[0])))
                except Exception:
                    val = 100
            speech = f"Đã {'tắt' if val==0 else 'điều chỉnh'} đèn rọi Subsea {'về 0%' if val==0 else f'lên {val}%'}."
            out = AgentOutputSchema(intent="control", tool_call=AgentToolCall(action=action, params={"value": val}), speech_response=speech)
            return self._evaluate_safety_and_build(out)

        # 4. Telemetry Inquiry (Nhiệm vụ 3: Truy xuất Viễn trắc thời gian thực)
        elif any(k in text_lower for k in ["pin", "dung lượng"]):
            battery_pct = telemetry.get("battery_pct", 85)
            voltage = telemetry.get("voltage", 16.8)
            speech = f"Dung lượng pin ROV hiện tại còn {battery_pct}%, điện áp {voltage:.1f}V."
            out = AgentOutputSchema(intent="query_telemetry", speech_response=speech)
            return out, None

        elif any(k in text_lower for k in ["nhiệt độ", "nhiệt"]):
            temp = telemetry.get("internal_temp_c", telemetry.get("temp", 28.5))
            speech = f"Nhiệt độ khoang máy hiện tại là {temp:.1f}°C."
            out = AgentOutputSchema(intent="query_telemetry", speech_response=speech)
            return out, None

        elif any(k in text_lower for k in ["độ sâu", "mặt nước"]):
            speech = f"Robot đang ở độ sâu {depth:.2f}m."
            out = AgentOutputSchema(intent="query_telemetry", speech_response=speech)
            return out, None

        elif any(k in text_lower for k in ["điện áp", "volts", "vôn"]):
            voltage = telemetry.get("voltage", 16.8)
            speech = f"Điện áp hệ thống tether hiện tại là {voltage:.1f}V."
            out = AgentOutputSchema(intent="query_telemetry", speech_response=speech)
            return out, None

        elif any(k in text_lower for k in ["thông số", "cảm biến", "viễn trắc"]):
            voltage = telemetry.get("voltage", 16.8)
            battery_pct = telemetry.get("battery_pct", 85)
            temp = telemetry.get("internal_temp_c", 28.5)
            speech = f"Báo cáo viễn trắc VIC: Độ sâu {depth:.2f}m, Điện áp {voltage:.1f}V, Pin {battery_pct}%, Nhiệt độ {temp:.1f}°C."
            out = AgentOutputSchema(intent="query_telemetry", speech_response=speech)
            return out, None

        # 5. Default Chat Response
        speech = f"CNX VIC nghe rõ: '{text}'."
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
