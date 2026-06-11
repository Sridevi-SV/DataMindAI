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
        self.provider_used = ""
        self.llm_latency_sec = 0.0
        self.routing_reason = ""
        self.latency_ms = 0
        self.answer = ""

def run_agent_loop(question: str, dataset_id: int = None, mcp_client=None) -> AgentLoopExecution:
    start_time = time.time()
    exec_state = AgentLoopExecution(question)
    
    # Query database for the active dataset details
    dataset_name = "Unknown"
    columns = []
    row_count = 0
    schema_summary = ""
    
    if dataset_id is not None:
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Fetch dataset details
            cursor.execute("SELECT name, row_count FROM datasets WHERE id = ?", (dataset_id,))
            ds_row = cursor.fetchone()
            if ds_row:
                dataset_name = ds_row[0]
                row_count = ds_row[1]
                
            # Fetch tables and columns
            cursor.execute("SELECT id, name, row_count, description FROM tables WHERE dataset_id = ?", (dataset_id,))
            tables = cursor.fetchall()
            
            schema_parts = []
            for t in tables:
                table_id, tname, t_row_count, tdesc = t
                cursor.execute("SELECT name, data_type, sample_values_json, description FROM columns WHERE table_id = ?", (table_id,))
                cols = cursor.fetchall()
                table_cols = []
                for col in cols:
                    cname, ctype, sample_json, cdesc = col
                    columns.append(cname)
                    try:
                        samples = json.loads(sample_json) if sample_json else []
                    except Exception:
                        samples = []
                    sample_str = ", ".join(map(str, samples[:3]))
                    table_cols.append(f"  - {cname} ({ctype}): {cdesc or ''} | Samples: [{sample_str}]")
                
                schema_parts.append(f"Table: {tname} (Row count: {t_row_count}, Description: {tdesc or ''})\n" + "\n".join(table_cols))
            
            schema_summary = "\n\n".join(schema_parts)
            conn.close()
        except Exception as e:
            print(f"[AI COPILOT] Error fetching schema metadata: {str(e)}")
            
    # Add diagnostic logging exactly as required
    print(f"[AI COPILOT] Active Dataset: {dataset_name}")
    print(f"[AI COPILOT] Columns: {columns}")
    print(f"[AI COPILOT] Row Count: {row_count}")
    
    # 0. NUMERICAL QUERY DETECTION & SQL GROUNDED COMPUTATION
    numerical_keywords = [
        "average", "mean", "median", "count", "total", "sum", 
        "minimum", "maximum", "highest", "lowest", "percentage", "attrition rate"
    ]
    is_numerical = any(kw in question.lower() for kw in numerical_keywords)
    
    if is_numerical and dataset_id is not None:
        exec_state.intent = "SQL"
        exec_state.plan = [
            "Detect numerical query intent",
            "Generate dialect-compliant SQL via generate_sql tool",
            "Execute SQL query safely to fetch computed numeric results",
            "Explain calculations and query output using the LLM manager"
        ]
        exec_state.selected_tools = ["generate_sql", "query_database"]
        exec_state.model_used = "gemini-2.5-flash"
        exec_state.routing_reason = "Numerical Grounded Computation"
        
        try:
            from backend.mcp_server import mcp_server
            sql_res = mcp_server.call_tool("generate_sql", {"question": question, "dataset_id": dataset_id})
            
            if isinstance(sql_res, dict) and sql_res.get("is_valid"):
                sql_query = sql_res.get("generated_sql")
                exec_state.tool_results["generate_sql"] = sql_res
                
                if sql_query:
                    # Execute query safely
                    q_res = mcp_server.call_tool("query_database", {"sql_query": sql_query, "dataset_id": dataset_id})
                    exec_state.tool_results["query_database"] = q_res
                    
                    if isinstance(q_res, dict) and "error" not in q_res and "columns" in q_res and "rows" in q_res:
                        cols_out = q_res["columns"]
                        rows_out = q_res["rows"]
                        
                        # Feed actual result to LLM for explanation
                        explain_prompt = f"""
                        User Question: {question}
                        Generated SQL: {sql_query}
                        Calculated Query Result:
                        Columns: {cols_out}
                        Rows: {rows_out}
                        
                        Please generate a concise, business-friendly explanation of this query result for the user.
                        You MUST explain only using the calculated query result.
                        """
                        ans_text, provider, model, route_info, latency_sec = generate_response(
                            explain_prompt, 
                            system_instruction=f"You explain database query results. The active dataset is {dataset_name}."
                        )
                        if model == "ERROR":
                            from ai.llm_manager import clean_error_message
                            exec_state.answer = f"AI service is currently unavailable. Details: {clean_error_message(ans_text)}"
                        else:
                            exec_state.answer = ans_text
                        exec_state.model_used = model
                        exec_state.provider_used = provider
                        exec_state.llm_latency_sec = latency_sec
                        exec_state.routing_reason = "Numerical Grounded Computation"
                        exec_state.validation_status = "PASSED"
                        
                        # Save to memory
                        memory.save_context({"input": question}, {"output": exec_state.answer})
                        exec_state.latency_ms = int((time.time() - start_time) * 1000)
                        
                        # Log and return
                        add_agent_log(
                            question=exec_state.question,
                            intent=exec_state.intent,
                            plan=exec_state.plan,
                            tools_used=exec_state.selected_tools,
                            context_retrieved=[],
                            validation_status=exec_state.validation_status,
                            response=exec_state.answer,
                            latency_ms=exec_state.latency_ms,
                            model_used=exec_state.model_used
                        )
                        return exec_state
                    else:
                        exec_state.answer = "No relevant information found in the selected dataset."
                else:
                    exec_state.answer = "No relevant information found in the selected dataset."
            else:
                exec_state.answer = "No relevant information found in the selected dataset."
        except Exception as e:
            exec_state.answer = "No relevant information found in the selected dataset."
            
        exec_state.validation_status = "FAILED"
        exec_state.latency_ms = int((time.time() - start_time) * 1000)
        add_agent_log(
            question=exec_state.question,
            intent=exec_state.intent,
            plan=exec_state.plan,
            tools_used=exec_state.selected_tools,
            context_retrieved=[],
            validation_status=exec_state.validation_status,
            response=exec_state.answer,
            latency_ms=exec_state.latency_ms,
            model_used=exec_state.model_used
        )
        return exec_state

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
    intent_out, provider, model, route_info, latency_sec = generate_response(intent_prompt, system_instruction="You are a routing classification agent.")
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
    client_to_use = mcp_client
    if not client_to_use:
        try:
            from backend.mcp_server import mcp_server
            client_to_use = mcp_server
        except Exception:
            pass
            
    if client_to_use:
        for tool in exec_state.selected_tools:
            try:
                # Execute tool using the registered functions
                result = client_to_use.call_tool(tool, {"question": question, "dataset_id": dataset_id})
                exec_state.tool_results[tool] = result
            except Exception as e:
                exec_state.tool_results[tool] = {"error": f"Tool Execution failed: {str(e)}"}
                
    # 4. CONTEXT RETRIEVAL (RAG)
    # Search ChromaDB vector store with dataset_id filter to avoid context leakages
    rag_hits = retrieve_context(question, dataset_id=dataset_id, top_k=4)
    exec_state.context_retrieved = [hit["document"] for hit in rag_hits]
    
    # Check if context is completely empty (no RAG context, no schema metadata, no tool outputs)
    has_rag_context = bool(exec_state.context_retrieved)
    has_metadata = bool(schema_summary.strip())
    
    has_tool_output = False
    if exec_state.tool_results:
        for val in exec_state.tool_results.values():
            if val and not (isinstance(val, dict) and "error" in val):
                if isinstance(val, dict):
                    if any(v for v in val.values() if v):
                        has_tool_output = True
                else:
                    has_tool_output = True
                    
    if not (has_rag_context or has_metadata or has_tool_output):
        exec_state.answer = "No relevant information found in the selected dataset."
        exec_state.validation_status = "PASSED"
        exec_state.latency_ms = int((time.time() - start_time) * 1000)
        
        # Log and return
        add_agent_log(
            question=exec_state.question,
            intent=exec_state.intent,
            plan=exec_state.plan,
            tools_used=exec_state.selected_tools,
            context_retrieved=[],
            validation_status=exec_state.validation_status,
            response=exec_state.answer,
            latency_ms=exec_state.latency_ms,
            model_used=exec_state.model_used
        )
        return exec_state
    
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
    
    Active Dataset: {dataset_name}
    Row Count: {row_count}
    
    Currently Selected Dataset Schema Context:
    {schema_summary}
    
    User Question: {question}
    Detected Intent: {exec_state.intent}
    
    Relevant Catalog Schema Context (RAG):
    {rag_context_summary}
    
    MCP Tool Call Results:
    {tool_results_summary}
    
    Previous Chat Context:
    {chat_history_str}
    
    CRITICAL INSTRUCTIONS:
    1. Address the user question directly, accurately, and professionally.
    2. Answer ONLY using the schema, columns, and metadata of the currently selected active dataset ({dataset_name}).
    3. Do NOT reference older datasets (such as college_faq_dataset or sample datasets) unless the user explicitly asks about them.
    4. Do NOT generate markdown tables containing raw sensitive database records.
    5. If explaining table schemas, reference columns clearly.
    6. If the retrieved context is empty, or you cannot find verified information in the provided context, you MUST return exactly:
       "No relevant information found in the selected dataset."
    7. Never invent values.
    8. Never fabricate statistics.
    9. Never assume table contents.
    10. Never generate business explanations unless supported by the retrieved context.
    """
    
    ans_text, provider, model, route_info, latency_sec = generate_response(reasoning_prompt, system_instruction=f"You are a data catalog intelligence expert. The active dataset is {dataset_name}.")
    if model == "ERROR":
        from ai.llm_manager import clean_error_message
        exec_state.answer = f"AI service is currently unavailable. Details: {clean_error_message(ans_text)}"
    else:
        exec_state.answer = ans_text
    exec_state.model_used = model
    exec_state.provider_used = provider
    exec_state.llm_latency_sec = latency_sec
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
