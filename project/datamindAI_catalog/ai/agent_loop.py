import time
import json
from ai.llm_manager import generate_response
from ai.vector_store import retrieve_context
from backend.database import get_db_connection, add_agent_log

# Self-contained Memory class to avoid external dependency package conflicts
class LocalConversationBufferMemory:
    def __init__(self, memory_key="chat_history", return_messages=True):
        self.memory_key = memory_key
        self.messages = []
        
    def load_memory_variables(self, inputs=None):
        history = ""
        for msg in self.messages:
            history += f"{msg['role']}: {msg['content']}\n"
        return {self.memory_key: history}
        
    def save_context(self, inputs, outputs):
        user_msg = inputs.get("input", "")
        ai_msg = outputs.get("output", "")
        self.messages.append({"role": "User", "content": user_msg})
        self.messages.append({"role": "Assistant", "content": ai_msg})

memory = LocalConversationBufferMemory(memory_key="chat_history", return_messages=True)

class AgentLoopExecution:
    def __init__(self, question):
        self.question = question
        self.intent = None
        self.plan = []
        self.selected_tools = []
        self.tool_results = {}
        self.context_retrieved = []
        self.reasoning = ""
        self.validation_status = "Not Validated"
        self.confidence_score = 0.85
        self.source_tables = []
        self.model_used = ""
        self.routing_reason = ""
        self.latency_ms = 0
        self.answer = ""

def run_agent_loop(question: str, dataset_id: int = None, mcp_client=None) -> AgentLoopExecution:
    start_time = time.time()
    exec_state = AgentLoopExecution(question)
    
    # Load memory history context
    history = memory.load_memory_variables({})
    chat_history_str = history.get("chat_history", "")
    
    # 1. INTENT DETECTION
    intent_prompt = f"""
    You are the Router for DataMind AI. Classify the user query into exactly one of these categories:
    - METADATA: Questions about what tables, columns, schemas exist.
    - RELATIONSHIP: Questions about table links, joins, primary/foreign keys.
    - QUALITY: Questions about health, nulls, duplicates, outliers, health scores.
    - SQL: Questions requesting SQL code or query execution.
    - GLOSSARY: Questions about business terms, meanings, usage.
    - BUSINESS: Questions asking for descriptions, context, business explanations, or general business concepts.

    Previous chat context:
    {chat_history_str}

    User Question: "{question}"
    
    Respond with ONLY the category name in uppercase.
    """
    intent_out, _, _ = generate_response(intent_prompt, system_instruction="You are a routing classification agent.")
    exec_state.intent = intent_out.strip().upper()
    if exec_state.intent not in ["METADATA", "RELATIONSHIP", "QUALITY", "SQL", "GLOSSARY", "BUSINESS"]:
        exec_state.intent = "BUSINESS" # Default fallback
        
    # 2. PLANNING
    # Make a plan based on the intent
    if exec_state.intent == "METADATA":
        exec_state.plan = [
            "Detect schema metadata intent",
            "Search ChromaDB vector store for matching tables/columns",
            "Query local SQLite catalog metadata for verified schema",
            "Synthesize schema overview response"
        ]
        exec_state.selected_tools = ["schema_explorer", "catalog_search"]
        
    elif exec_state.intent == "RELATIONSHIP":
        exec_state.plan = [
            "Detect relationship discovery intent",
            "Call relationship_discovery tool to find linkages",
            "Verify join capabilities and overlaps",
            "Construct network path overview and recommendations"
        ]
        exec_state.selected_tools = ["relationship_discovery"]
        
    elif exec_state.intent == "QUALITY":
        exec_state.plan = [
            "Detect data quality scanner intent",
            "Retrieve quality scan profile for the tables",
            "Check for duplicates, missing ratios, outliers",
            "Format data health audit response"
        ]
        exec_state.selected_tools = ["quality_scan"]
        
    elif exec_state.intent == "SQL":
        exec_state.plan = [
            "Detect text-to-SQL generation intent",
            "Retrieve database schema metadata",
            "Generate dialect-compliant SQL structure",
            "Run local validation to check columns and tables",
            "Explain generated query steps"
        ]
        exec_state.selected_tools = ["generate_sql", "query_database"]
        
    elif exec_state.intent == "GLOSSARY":
        exec_state.plan = [
            "Detect business glossary query intent",
            "Look up term definitions in glossary catalog",
            "Explain semantic usage and business mapping"
        ]
        exec_state.selected_tools = ["business_glossary"]
        
    else: # BUSINESS
        exec_state.plan = [
            "Detect general business logic / explain intent",
            "Search RAG vector database for semantic schema descriptions",
            "Apply AI context reasoning to link business term to columns",
            "Generate business-friendly explanation"
        ]
        exec_state.selected_tools = ["describe_table", "describe_column"]
        
    # 3. TOOL SELECTION & EXECUTION
    # Call our local MCP tools programmatically
    # (Since this agent consumes the MCP registry locally)
    if mcp_client:
        for tool in exec_state.selected_tools:
            try:
                # Execute tool using the registered functions in mcp_client
                result = mcp_client.call_tool(tool, {"question": question, "dataset_id": dataset_id})
                exec_state.tool_results[tool] = result
            except Exception as e:
                exec_state.tool_results[tool] = f"Tool Execution failed: {str(e)}"
                
    # 4. CONTEXT RETRIEVAL (RAG)
    # Search ChromaDB vector store
    rag_hits = retrieve_context(question, top_k=4)
    exec_state.context_retrieved = [hit["document"] for hit in rag_hits]
    
    # Extract source tables from vector hits
    for hit in rag_hits:
        meta = hit.get("metadata", {})
        if "table_name" in meta:
            exec_state.source_tables.append(meta["table_name"])
    exec_state.source_tables = list(set(exec_state.source_tables))
    
    # 5. REASONING
    # Synthesize the answer using the LLM manager
    tool_results_summary = json.dumps(exec_state.tool_results, indent=2)
    rag_context_summary = "\n---\n".join(exec_state.context_retrieved)
    
    reasoning_prompt = f"""
    You are the DataMind AI Intelligence Copilot. Synthesize an answer for the user query.
    
    User Question: {question}
    Detected Intent: {exec_state.intent}
    
    Relevant Catalog Schema Context (RAG):
    {rag_context_summary}
    
    MCP Tool Call Results:
    {tool_results_summary}
    
    Previous Chat Context:
    {chat_history_str}
    
    Instructions:
    - Address the user question directly, accurately, and professionally.
    - Do NOT generate markdown tables containing raw sensitive database records.
    - If explaining table schemas, reference columns clearly.
    - Provide a business-friendly response.
    """
    
    ans_text, model, route_info = generate_response(reasoning_prompt, system_instruction="You are a data catalog intelligence expert.")
    exec_state.answer = ans_text
    exec_state.model_used = model
    exec_state.routing_reason = route_info
    
    # Calculate simple confidence score based on model and hit coverage
    confidence = 0.90
    if "Fallback" in model:
        confidence -= 0.15 # local fallback slightly lower confidence
    if not exec_state.context_retrieved:
        confidence -= 0.10 # no RAG context
    exec_state.confidence_score = round(max(confidence, 0.50), 2)
    
    # 6. VALIDATION
    # Post-validation scan (Check for PII leaks or SQL injection keywords if not safe)
    validation_status = "PASSED"
    if "[MASKED_" in ans_text or "[REDACTED_" in ans_text:
        validation_status = "PII_MASKED"
    
    # Ensure raw record data is not sent
    if "email" in question.lower() or "select" in ans_text.lower():
        # Double check if raw rows are outputted
        if "@" in ans_text and not "[REDACTED_EMAIL]" in ans_text:
            validation_status = "REJECTED_RAW_DATA"
            exec_state.answer = "Access Denied: The query generated output containing raw customer contact information, which violates the enterprise security catalog policy."
            
    exec_state.validation_status = validation_status
    
    # Save to Memory
    memory.save_context({"input": question}, {"output": exec_state.answer})
    
    # 7. LOG AND RETURN
    exec_state.latency_ms = int((time.time() - start_time) * 1000)
    
    # Store in database logs
    add_agent_log(
        question=exec_state.question,
        intent=exec_state.intent,
        plan=exec_state.plan,
        tools_used=exec_state.selected_tools,
        context_retrieved=exec_state.context_retrieved,
        validation_status=exec_state.validation_status,
        response=exec_state.answer,
        latency_ms=exec_state.latency_ms,
        model_used=exec_state.model_used
    )
    
    return exec_state
