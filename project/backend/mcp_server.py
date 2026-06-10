import json
import sqlite3
from backend.database import get_db_connection
from engines.sql_copilot import validate_sql_against_schema, execute_safe_query, generate_schema_context_prompt
from engines.glossary import get_glossary_terms
from ai.llm_manager import generate_response

class MCPServerRegistry:
    def __init__(self):
        self.tools = {}
        self.register_all_tools()
        
    def register(self, name, description, schema_dict):
        def decorator(func):
            self.tools[name] = {
                "func": func,
                "description": description,
                "schema": schema_dict
            }
            return func
        return decorator

    def call_tool(self, name, arguments):
        if name not in self.tools:
            raise ValueError(f"Tool '{name}' is not registered on this MCP server.")
        return self.tools[name]["func"](**arguments)
        
    def list_tools(self):
        return [
            {
                "name": name,
                "description": info["description"],
                "input_schema": info["schema"]
            }
            for name, info in self.tools.items()
        ]

    def register_all_tools(self):
        # 1. schema_explorer
        @self.register(
            "schema_explorer",
            "Lists all tables, columns, and data types in the catalog database for a given dataset.",
            {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "integer", "description": "The unique identifier of the dataset catalog"}
                },
                "required": ["dataset_id"]
            }
        )
        def schema_explorer(dataset_id, **kwargs):
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT id, name, row_count, description FROM tables WHERE dataset_id = ?", (dataset_id,))
                tables = [dict(row) for row in cursor.fetchall()]
                
                for t in tables:
                    cursor.execute("SELECT name, data_type, description, is_pii FROM columns WHERE table_id = ?", (t["id"],))
                    t["columns"] = [dict(row) for row in cursor.fetchall()]
                return {"dataset_id": dataset_id, "tables": tables}
            finally:
                conn.close()

        # 2. catalog_search
        @self.register(
            "catalog_search",
            "Performs text search on schemas, column names, descriptions, and metadata matching a keyword query.",
            {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The query word or phrase to look for"}
                },
                "required": ["question"]
            }
        )
        def catalog_search(question, dataset_id=None, **kwargs):
            conn = get_db_connection()
            cursor = conn.cursor()
            search_query = f"%{question}%"
            try:
                # Find matching columns
                cursor.execute(
                    """SELECT c.name as column_name, c.data_type, c.description as column_desc, t.name as table_name, t.description as table_desc 
                       FROM columns c 
                       JOIN tables t ON c.table_id = t.id 
                       WHERE c.name LIKE ? OR c.description LIKE ? OR t.name LIKE ? OR t.description LIKE ?""",
                    (search_query, search_query, search_query, search_query)
                )
                matches = [dict(row) for row in cursor.fetchall()]
                return {"matches": matches[:20]} # limit output size
            finally:
                conn.close()

        # 3. describe_table
        @self.register(
            "describe_table",
            "Returns technical stats, row count, and business summary description for a table.",
            {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "integer", "description": "The dataset ID"},
                    "table_name": {"type": "string", "description": "Exact name of the table to explain"}
                },
                "required": ["dataset_id", "table_name"]
            }
        )
        def describe_table(table_name, dataset_id=None, **kwargs):
            if not dataset_id:
                return {"error": "dataset_id is required."}
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT * FROM tables WHERE dataset_id = ? AND name = ?", (dataset_id, table_name))
                tbl = cursor.fetchone()
                if not tbl:
                    return {"error": f"Table '{table_name}' not found."}
                    
                tbl_dict = dict(tbl)
                cursor.execute("SELECT name, data_type, description, is_pii, distinct_count, null_count FROM columns WHERE table_id = ?", (tbl_dict["id"],))
                tbl_dict["columns"] = [dict(row) for row in cursor.fetchall()]
                return tbl_dict
            finally:
                conn.close()

        # 4. describe_column
        @self.register(
            "describe_column",
            "Returns the detailed description, sample values, null counts, distinct counts, and PII status for a column.",
            {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "The table name"},
                    "column_name": {"type": "string", "description": "The column name"}
                },
                "required": ["table_name", "column_name"]
            }
        )
        def describe_column(table_name, column_name, dataset_id=None, **kwargs):
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                # Find column by name and parent table name
                cursor.execute(
                    """SELECT c.* FROM columns c 
                       JOIN tables t ON c.table_id = t.id 
                       WHERE t.name = ? AND c.name = ?""",
                    (table_name, column_name)
                )
                col = cursor.fetchone()
                if not col:
                    return {"error": f"Column '{column_name}' not found in table '{table_name}'."}
                col_dict = dict(col)
                # Parse sample values json safety
                if col_dict.get("sample_values_json"):
                    col_dict["sample_values"] = json.loads(col_dict["sample_values_json"])
                return col_dict
            finally:
                conn.close()

        # 5. relationship_discovery
        @self.register(
            "relationship_discovery",
            "Lists all discovered table joins, relationships, primary keys, and confidence levels for a dataset.",
            {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "integer", "description": "The dataset ID"}
                },
                "required": ["dataset_id"]
            }
        )
        def relationship_discovery(dataset_id, **kwargs):
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT * FROM relationships WHERE dataset_id = ?", (dataset_id,))
                rels = [dict(row) for row in cursor.fetchall()]
                # Parse details json
                for r in rels:
                    if r.get("details_json"):
                        r["details"] = json.loads(r["details_json"])
                return {"relationships": rels}
            finally:
                conn.close()

        # 6. quality_scan
        @self.register(
            "quality_scan",
            "Retrieves the data health scores, duplicate counts, outlier fields, format checks, and suggestions.",
            {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "integer", "description": "The dataset ID"},
                    "table_name": {"type": "string", "description": "Table name to scan, or empty to scan all"}
                },
                "required": ["dataset_id"]
            }
        )
        def quality_scan(dataset_id, table_name=None, **kwargs):
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                if table_name:
                    cursor.execute("SELECT * FROM quality_metrics WHERE dataset_id = ? AND table_name = ?", (dataset_id, table_name))
                else:
                    cursor.execute("SELECT * FROM quality_metrics WHERE dataset_id = ?", (dataset_id,))
                metrics = [dict(row) for row in cursor.fetchall()]
                for m in metrics:
                    if m.get("details_json"):
                        m["details"] = json.loads(m["details_json"])
                    if m.get("recommendations_json"):
                        m["recommendations"] = json.loads(m["recommendations_json"])
                return {"metrics": metrics}
            finally:
                conn.close()

        # 7. generate_sql
        @self.register(
            "generate_sql",
            "Translates a natural language user question into validated standard SQL script.",
            {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The user request"},
                    "dataset_id": {"type": "integer", "description": "The dataset ID"}
                },
                "required": ["question", "dataset_id"]
            }
        )
        def generate_sql(question, dataset_id, **kwargs):
            # 1. Fetch schemas for context
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT id, name, description FROM tables WHERE dataset_id = ?", (dataset_id,))
                tables = [dict(row) for row in cursor.fetchall()]
                
                catalog_schema = {}
                tables_meta = []
                for t in tables:
                    cursor.execute("SELECT name, data_type, description, is_pii FROM columns WHERE table_id = ?", (t["id"],))
                    columns = [dict(row) for row in cursor.fetchall()]
                    t["columns"] = columns
                    tables_meta.append(t)
                    
                    catalog_schema[t["name"]] = {
                        "columns": [c["name"] for c in columns],
                        "is_pii": [c["name"] for c in columns if c["is_pii"] == 1]
                    }
            finally:
                conn.close()
                
            schema_prompt = generate_schema_context_prompt(tables_meta)
            
            prompt = f"""
            You are a SQL Architect. Generate standard SQL query based on the following user question and schema context.
            
            User Question: {question}
            
            Schema Context:
            {schema_prompt}
            
            Instructions:
            - Output ONLY the raw SQL code block. Do NOT surround it with markdown fences like ```sql. Do NOT provide explanation.
            - Ensure generated SQL is correct, safe, and uses standard ANSI SQL.
            - If sensitive PII fields (marked SENSITIVE) are referenced, never output them raw in SELECT without aggregates, or make sure they are aggregates.
            """
            
            sql_query, _, _ = generate_response(prompt, system_instruction="You output ONLY standard SQL code. No explanation.")
            sql_query = sql_query.strip(" `\n\r\t").replace("sql\n", "").strip()
            
            # Run validation checks
            is_valid, err = validate_sql_against_schema(sql_query, catalog_schema)
            
            return {
                "generated_sql": sql_query,
                "is_valid": is_valid if err is None else False,
                "validation_error": err
            }

        # 8. dataset_summary
        @self.register(
            "dataset_summary",
            "Returns top-level metadata statistics of a dataset catalog, such as row count and table/column counts.",
            {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "integer", "description": "The dataset ID"}
                },
                "required": ["dataset_id"]
            }
        )
        def dataset_summary(dataset_id, **kwargs):
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
                ds = cursor.fetchone()
                if not ds:
                    return {"error": f"Dataset {dataset_id} not found."}
                ds_dict = dict(ds)
                
                cursor.execute("SELECT COUNT(*) FROM tables WHERE dataset_id = ?", (dataset_id,))
                table_count = cursor.fetchone()[0]
                
                cursor.execute(
                    "SELECT COUNT(*) FROM columns c JOIN tables t ON c.table_id = t.id WHERE t.dataset_id = ?",
                    (dataset_id,)
                )
                column_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM relationships WHERE dataset_id = ?", (dataset_id,))
                rel_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT AVG(health_score) FROM quality_metrics WHERE dataset_id = ?", (dataset_id,))
                avg_health = cursor.fetchone()[0] or 100.0
                
                return {
                    "name": ds_dict["name"],
                    "type": ds_dict["type"],
                    "uploaded_at": ds_dict["uploaded_at"],
                    "total_tables": table_count,
                    "total_columns": column_count,
                    "relationships_found": rel_count,
                    "health_score": round(avg_health, 1)
                }
            finally:
                conn.close()

        # 9. query_database
        @self.register(
            "query_database",
            "Executes a validated SQL query safely on the database source locally, returning results limited to 50 rows.",
            {
                "type": "object",
                "properties": {
                    "dataset_id": {"type": "integer", "description": "The dataset ID"},
                    "sql_query": {"type": "string", "description": "Standard SQL query string to run"}
                },
                "required": ["dataset_id", "sql_query"]
            }
        )
        def query_database(sql_query, dataset_id, **kwargs):
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT type, file_path FROM datasets WHERE id = ?", (dataset_id,))
                ds = cursor.fetchone()
                if not ds:
                    return {"error": f"Dataset {dataset_id} not found."}
                ds_type, ds_path = ds[0], ds[1]
            finally:
                conn.close()
                
            try:
                # Execute safely
                df = execute_safe_query(sql_query, ds_type, ds_path, max_rows=50)
                
                # Check for PII fields in output and mask them
                # This guarantees that raw records are NEVER sent to AI panel or displayed unmasked
                for col in df.columns:
                    # Let's inspect column names
                    col_lower = col.lower()
                    is_col_pii = False
                    for pattern in ["email", "phone", "mobile", "address", "card", "salary", "ssn", "password"]:
                        if pattern in col_lower:
                            is_col_pii = True
                            break
                    if is_col_pii:
                        # Mask values
                        from engines.data_loader import mask_sensitive_value
                        df[col] = df[col].apply(lambda x: mask_sensitive_value(x, col))
                        
                return {
                    "columns": list(df.columns),
                    "rows": df.values.tolist(),
                    "row_count": len(df)
                }
            except Exception as e:
                return {"error": f"SQL Execution Error: {str(e)}"}

        # 10. business_glossary
        @self.register(
            "business_glossary",
            "Searches or queries definitions and usage details from the Business Glossary.",
            {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The term to look up, or empty to list all"}
                },
                "required": []
            }
        )
        def business_glossary(question=None, **kwargs):
            terms = get_glossary_terms(question)
            return {"terms": terms}

mcp_server = MCPServerRegistry()
print("MCP Server built and registry tools loaded successfully.")
