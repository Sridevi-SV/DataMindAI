import pytest
from unittest.mock import patch, MagicMock
from ai.agent_loop import run_agent_loop, memory

@patch("ai.agent_loop.generate_response")
def test_agent_loop_routing_and_planning(mock_generate_response):
    # Mock routing to QUALITY, then mock reasoning response
    mock_generate_response.side_effect = [
        # Call 1: Intent detection
        ("QUALITY", "gemini-1.5-flash", "Classified as data quality"),
        # Call 2: Final response reasoning
        ("Mock data quality answer showing schema health metrics.", "gemini-1.5-flash", "Standard response")
    ]
    
    # Exec loop
    exec_state = run_agent_loop("Check duplicates on customer billing tables", dataset_id=1)
    
    # Verify states
    assert exec_state.intent == "QUALITY"
    assert "quality_scan" in exec_state.selected_tools
    assert len(exec_state.plan) > 0
    assert exec_state.validation_status == "PASSED"
    assert "Mock data quality" in exec_state.answer
    
    # Check that memory records context
    history = memory.load_memory_variables({})
    assert "chat_history" in history

@patch("ai.agent_loop.generate_response")
def test_agent_loop_pii_security_compliance(mock_generate_response):
    # Mock routing to SQL, then mock returning raw PII emails in SQL response
    mock_generate_response.side_effect = [
        # Call 1: Intent detection
        ("SQL", "gemini-1.5-flash", "Classified as SQL"),
        # Call 2: Final response reasoning containing actual raw emails (which triggers rejection)
        ("Here is the requested email list: Alice (alice@gmail.com), Bob (bob@gmail.com)", "gemini-1.5-flash", "Standard response")
    ]
    
    # Exec loop asking specifically for email output (should trigger PII validation block)
    exec_state = run_agent_loop("Show all customer email records", dataset_id=1)
    
    # Verify validation catches this and returns security block message
    assert exec_state.validation_status in ["PII_MASKED", "REJECTED_RAW_DATA"]
    if exec_state.validation_status == "REJECTED_RAW_DATA":
        assert "Access Denied" in exec_state.answer
