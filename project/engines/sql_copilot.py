import re
import sqlite3
import pandas as pd
from sqlalchemy import create_engine, text

def extract_tables_from_sql(sql_query):
    """
    Extracts table names from a standard SQL SELECT query using regex.
    """
    # Remove comments and strings to prevent false positives
    query = re.sub(r'--.*?\n', '', sql_query)
    query = re.sub(r'/\*.*?\*/', '', query, flags=re.DOTALL)
    
    # Matches: FROM table_name, JOIN table_name
    pattern = r'(?:FROM|JOIN)\s+[`"\[]?([\w\.-]+)[`"\]]?'
    tables = re.findall(pattern, query, re.IGNORECASE)
    
    # Clean up schema prefixes (e.g. public.users -> users)
    clean_tables = []
    for t in tables:
        parts = t.split('.')
        clean_tables.append(parts[-1].strip('`"[]'))
        
    return list(set(clean_tables))

def validate_sql_against_schema(sql_query, catalog_schema):
    """
    Validates SQL query against catalog metadata.
    """
    try:
        if not catalog_schema or not isinstance(catalog_schema, dict):
            return False, "Catalog schema metadata is missing or invalid."
            
        referenced_tables = extract_tables_from_sql(sql_query)
        if not referenced_tables:
            return False, "Could not extract any tables from the generated SQL query."
            
        for table in referenced_tables:
            if not table:
                continue
            schema_keys = [t for t in catalog_schema.keys() if t]
            if table.lower() not in [t.lower() for t in schema_keys]:
                return False, f"Table '{table}' referenced in SQL does not exist in the dataset catalog."
                
            # Find exact case table in catalog
            exact_table_name = next((t for t in schema_keys if t.lower() == table.lower()), None)
            if not exact_table_name:
                return False, f"Table '{table}' referenced in SQL does not exist in the dataset catalog."
                
            table_info = catalog_schema.get(exact_table_name)
            if not table_info or not isinstance(table_info, dict):
                return False, f"Schema columns not found for table '{exact_table_name}'."
                
            allowed_columns = [c.lower() for c in table_info.get("columns", []) if c]
            
            # Check columns referenced in query
            words = re.findall(r'\b\w+\b', sql_query)
            for word in words:
                if '.' in word:
                    parts = word.split('.')
                    if len(parts) >= 2:
                        prefix, col = parts[0], parts[1]
                        if prefix.lower() == table.lower() and col.lower() not in allowed_columns:
                            return False, f"Column '{col}' does not exist on table '{exact_table_name}'."
                            
        return True, None
    except Exception as e:
        return False, f"An error occurred during SQL validation: {str(e)}"

def execute_safe_query(sql_query, ds_type, ds_path, max_rows=50):
    """
    Executes a generated SQL query locally on SQLite or PostgreSQL,
    enforcing a row limit for UI display and memory performance.
    Supports CSV and JSON by dynamically loading them into an in-memory SQLite table.
    """
    # Enforce LIMIT
    sql_stripped = sql_query.strip().rstrip(';')
    if "LIMIT" not in sql_stripped.upper() and ds_type.upper() in ('SQLITE', 'CSV', 'JSON'):
        sql_stripped += f" LIMIT {max_rows}"
    
    if ds_type.upper() == 'SQLITE':
        conn = sqlite3.connect(ds_path)
        try:
            df = pd.read_sql_query(sql_stripped, conn)
            return df
        finally:
            conn.close()
            
    elif ds_type.upper() == 'POSTGRESQL':
        engine = create_engine(ds_path)
        try:
            # If PostgreSQL, append limit in a dialect-safe way if needed
            if "LIMIT" not in sql_stripped.upper():
                sql_stripped += f" LIMIT {max_rows}"
            with engine.connect() as conn:
                df = pd.read_sql_query(text(sql_stripped), conn)
                return df
        finally:
            engine.dispose()
            
    elif ds_type.upper() in ('CSV', 'JSON'):
        import os
        import json
        
        # Load DataFrame
        if ds_type.upper() == 'CSV':
            df = pd.read_csv(ds_path)
        else: # JSON
            with open(ds_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                df = pd.json_normalize(data)
            elif isinstance(data, dict):
                array_key = None
                for k, v in data.items():
                    if isinstance(v, list):
                        array_key = k
                        break
                if array_key:
                    df = pd.json_normalize(data[array_key])
                else:
                    df = pd.json_normalize([data])
            else:
                raise ValueError("Invalid JSON format for query execution")
                
        # Find table name from metadata catalog for this dataset
        table_names = []
        db_path = "./data/metadata_catalog.db"
        if os.path.exists(db_path):
            conn_meta = sqlite3.connect(db_path)
            cursor_meta = conn_meta.cursor()
            try:
                cursor_meta.execute(
                    "SELECT t.name FROM tables t JOIN datasets d ON t.dataset_id = d.id WHERE d.file_path = ?",
                    (ds_path,)
                )
                table_names = [row[0] for row in cursor_meta.fetchall()]
            except Exception:
                pass
            finally:
                conn_meta.close()
                
        if not table_names:
            table_names = [os.path.splitext(os.path.basename(ds_path))[0]]
            
        # Write to in-memory SQLite database
        temp_conn = sqlite3.connect(":memory:")
        try:
            tbl_name = table_names[0]
            # Replace spaces and special characters in table name to ensure valid SQL execution
            tbl_name_clean = re.sub(r'[^a-zA-Z0-9_]', '_', tbl_name)
            df.to_sql(tbl_name_clean, temp_conn, index=False)
            
            # Map query references of the raw table name to the clean table name if needed
            # E.g., if query queries `WA_Fn-UseC_-HR-Employee-Attrition` but we wrote as WA_Fn_UseC__HR_Employee_Attrition
            sql_stripped_clean = sql_stripped
            if tbl_name != tbl_name_clean:
                sql_stripped_clean = re.sub(rf'\b{re.escape(tbl_name)}\b', tbl_name_clean, sql_stripped)
                # Check for quoted names too
                sql_stripped_clean = re.sub(rf'[`"\[]{re.escape(tbl_name)}[`"\]]', tbl_name_clean, sql_stripped_clean)
            
            res_df = pd.read_sql_query(sql_stripped_clean, temp_conn)
            return res_df
        finally:
            temp_conn.close()
def generate_schema_context_prompt(tables_metadata):
    """
    Converts tables_metadata into a clean text prompt showing table structures.
    Guarantees no raw records are sent.
    """
    if not isinstance(tables_metadata, list):
        return "No schema context available."
        
    context = []
    for table in tables_metadata:
        if not isinstance(table, dict):
            continue
        print("[SQL COPILOT] TABLE OBJECT:", table)
        table_name = (
            table.get("table_name")
            or table.get("name")
            or table.get("dataset_name")
        )
        if not table_name:
            continue
            
        columns_desc = []
        for col in table.get("columns", []):
            if not isinstance(col, dict):
                continue
            col_name = col.get("column_name") or col.get("name")
            if not col_name:
                continue
            col_type = col.get("data_type") or col.get("type", "TEXT")
            col_desc = col.get("description", "")
            pii_flag = " (PII - SENSITIVE)" if col.get("is_pii", 0) == 1 else ""
            columns_desc.append(f"  - {col_name} ({col_type}){pii_flag}: {col_desc}")
            
        context.append(
            f"Table: {table_name}\n"
            f"Description: {table.get('description', '')}\n"
            f"Columns:\n" + "\n".join(columns_desc)
        )
    return "\n\n".join(context)
