import pytest
import json
from backend.mcp_server import mcp_server

def test_mcp_registry_definitions():
    tools = mcp_server.list_tools()
    tool_names = [t["name"] for t in tools]
    
    # Check that all 10 tools are registered
    expected_tools = [
        "schema_explorer", "catalog_search", "describe_table", "describe_column", 
        "relationship_discovery", "quality_scan", "generate_sql", "dataset_summary", 
        "query_database", "business_glossary"
    ]
    
    for et in expected_tools:
        assert et in tool_names

def test_mcp_tool_business_glossary():
    # Execute business glossary tool mock call
    res = mcp_server.call_tool("business_glossary", {"question": "nonexistent_term"})
    assert "terms" in res
    # Since DB might be empty at test time, it should return a list
    assert isinstance(res["terms"], list)
