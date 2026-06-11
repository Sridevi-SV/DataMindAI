import pytest
import sqlite3
from unittest.mock import patch, MagicMock
from backend.database import get_db_connection, get_last_failover_event
from ai.llm_manager import generate_response, metadata_rule_engine

def test_metadata_rule_engine():
    # Test intent detection
    intent_prompt = """
    You are the Router for DataMind AI. Classify the user query into exactly one of these categories:
    - METADATA: Questions about what tables, columns, schemas exist.
    - RELATIONSHIP: Questions about table links, joins, primary/foreign keys.
    - QUALITY: Questions about health, nulls, duplicates, outliers, health scores.
    - SQL: Questions requesting SQL code or query execution.
    - GLOSSARY: Questions about business terms, meanings, usage.
    - BUSINESS: Questions asking for descriptions, context, business explanations, or general business concepts.

    Previous chat context:
    
    User Question: "Check duplicates on customer billing tables"
    
    Respond with ONLY the category name in uppercase.
    """
    assert metadata_rule_engine(intent_prompt) == "QUALITY"
    
    # Test table description
    desc_prompt = "Generate a short, business-friendly description for table customers"
    assert "customers" in metadata_rule_engine(desc_prompt)
    
    # Test column definition
    col_prompt = "Create a 5-word business definition for column: 'customer_id'"
    assert "customer_id" in metadata_rule_engine(col_prompt)

@patch("ai.llm_manager.call_gemini_api")
@patch("ai.llm_manager.call_groq_api")
def test_gemini_to_groq_failover(mock_call_groq, mock_call_gemini):
    # Mock Gemini to raise an exception, and Groq to return successfully
    mock_call_gemini.side_effect = Exception("Gemini Quota Exceeded")
    mock_call_groq.return_value = "This is response from Groq."
    
    # Run generate_response
    res, provider, model, route, latency = generate_response("test query")
    
    assert res == "This is response from Groq."
    assert provider == "Groq"
    assert model == "llama-3.3-70b-versatile"
    
    # Verify SQLite database has failover event logged
    last_event = get_last_failover_event()
    assert last_event is not None
    assert "Gemini Quota Exceeded" in last_event["error_message"]
    assert last_event["primary_model"] == "gemini-2.5-flash"
    assert last_event["fallback_model"] == "llama-3.3-70b-versatile"

@patch("ai.llm_manager.call_gemini_api")
@patch("ai.llm_manager.call_groq_api")
def test_groq_to_rule_engine_failover(mock_call_groq, mock_call_gemini):
    # Mock both Gemini and Groq to raise exceptions
    mock_call_gemini.side_effect = Exception("Gemini Connection Timeout")
    mock_call_groq.side_effect = Exception("Groq Service Unavailable")
    
    # Run generate_response
    res, provider, model, route, latency = generate_response("table name: users Generate a short, business-friendly description")
    
    assert provider == "Rule Engine"
    assert "users" in res
    
    # Verify SQLite database has second failover event logged
    last_event = get_last_failover_event()
    assert last_event is not None
    assert "Groq Service Unavailable" in last_event["error_message"]
    assert last_event["primary_model"] == "llama-3.3-70b-versatile"
    assert last_event["fallback_model"] == "Metadata Rule Engine"
