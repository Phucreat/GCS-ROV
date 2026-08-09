"""
test_ai_agent.py - Verification test for Offline AI Agent System
"""

import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from AI.safety_guard import SafetyGuard, CommandCategory
from AI.agent_brain import ROVAgentBrain, AgentOutputSchema

def run_tests():
    print("=== TEST 1: Safety Guard Categorization ===")
    sg = SafetyGuard()
    cat_read = sg.categorize_action("set_lights")
    cat_crit = sg.categorize_action("emergency_stop")
    print(f"set_lights category: {cat_read} (Expected: read_only)")
    print(f"emergency_stop category: {cat_crit} (Expected: critical)")
    assert cat_read == CommandCategory.READ_ONLY
    assert cat_crit == CommandCategory.CRITICAL

    print("\n=== TEST 2: Agent Brain Voice Command (Read-Only) ===")
    brain = ROVAgentBrain(sop_json_path=os.path.join(PROJECT_ROOT, "AI", "sop_rules.json"))
    telemetry = {"depth": 14.5, "voltage": 16.2, "mode": "STABILIZE"}
    
    out, action = brain.process_pilot_input("Hey VIC, bật đèn rọi 100%", telemetry, is_ptt=False)
    print(f"Speech response: {out.speech_response}")
    print(f"Action: {action}")
    assert action is not None and action["action"] == "set_lights"
    assert action["params"]["value"] == 100

    print("\n=== TEST 3: Agent Brain Voice Command (Critical Safety Confirmation) ===")
    out2, action2 = brain.process_pilot_input("ngắt động cơ khẩn cấp", telemetry, is_ptt=True)
    print(f"Confirmation Prompt: {out2.speech_response}")
    print(f"Immediate Action: {action2} (Expected: None)")
    assert action2 is None
    assert brain.safety_guard.has_pending_confirmation()

    # Confirm critical action
    out3, action3 = brain.process_pilot_input("xác nhận", telemetry, is_ptt=True)
    print(f"After confirmation speech: {out3.speech_response}")
    print(f"Confirmed Action: {action3}")
    assert action3 is not None and action3["action"] == "emergency_stop"
    assert not brain.safety_guard.has_pending_confirmation()

    print("\n=== TEST 4: Local SOP RAG Search ===")
    out4, _ = brain.process_pilot_input("VIC ơi cho tôi biết quy trình kiểm tra đường ống", telemetry, is_ptt=False)
    print(f"SOP RAG output: {out4.speech_response}")
    assert "đường ống" in out4.speech_response.lower() or "pipeline" in out4.speech_response.lower()

    print("\n✅ ALL AI AGENT SYSTEM VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
