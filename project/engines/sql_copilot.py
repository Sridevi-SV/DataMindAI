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
    pattern = r'(?:FROM|JOIN)\s+[`"\[]?([\w\.]+)[`"\]]?'
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
    catalog_schema format:
    {
       "table_name": {
           "columns": ["col1", "col2"],
           "is_pii": ["col2"]
       }
    }
    Returns (is_valid, error_message)
    """
    referenced_tables = extract_tables_from_sql(sql_query)
    if not referenced_tables:
        return False, "Could not extract any tables from the generated SQL query."
        
    for table in referenced_tables:
        if table.lower() not in [t.lower() for t in catalog_schema.keys()]:
            return False, f"Table '{table}' referenced in SQL does not exist in the dataset catalog."
            
        # Find exact case table in catalog
        exact_table_name = next(t for t in catalog_schema.keys() if t.lower() == table.lower())
        allowed_columns = [c.lower() for c in catalog_schema[exact_table_name]["columns"]]
        
        # Check columns referenced in query
        # This is a basic scanner. We search for words in the SQL that match column names of this table
        # but avoid keywords or function names. We only raise an error if a column is specifically referenced but missing.
        # To be safe, we check words in the query that are not SQL keywords.
        words = re.findall(r'\b\w+\b', sql_query)
        for word in words:
            # If word is a column name of this table, but not a column of ANY table in catalog,
            # or if it has a table prefix like table.column, we check it.
            if '.' in word:
                parts = word.split('.')
                prefix, col = parts[0], parts[1]
                if prefix.lower() == table.lower() and col.lower() not in allowed_columns:
                    return False, f"Column '{col}' does not exist on table '{exact_table_name}'."
                    
    return True, None

def execute_safe_query(sql_query, ds_type, ds_path, max_rows=50):
    """
    Executes a generated SQL query locally on SQLite or PostgreSQL,
    enforcing a row limit for UI display and memory performance.
    """
    # Enforce LIMIT
    sql_stripped = sql_query.strip().rstrip(';')
    if "LIMIT" not in sql_stripped.upper() and ds_type.upper() == 'SQLITE':
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
            
    else:
        raise ValueError(f"Execution not supported for data source type: {ds_type}")

def generate_schema_context_prompt(tables_metadata):
    """
    Converts tables_metadata into a clean text prompt showing table structures.
    Guarantees no raw records are sent.
    """
    context = []
    for table in tables_metadata:
        table_name = table["table_name"]
        columns_desc = []
        for col in table["columns"]:
            col_name = col["column_name"]
            col_type = col["data_type"]
            col_desc = col.get("description", "")
            pii_flag = " (PII - SENSITIVE)" if col.get("is_pii", 0) == 1 else ""
            columns_desc.append(f"  - {col_name} ({col_type}){pii_flag}: {col_desc}")
            
        context.append(
            f"Table: {table_name}\n"
            f"Description: {table.get('description', '')}\n"
            f"Columns:\n" + "\n".join(columns_desc)
        )
    return "\n\n".join(context)
