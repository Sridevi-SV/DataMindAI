import os
import re
import json
import sqlite3
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, inspect

# Regex for common PII patterns
PII_COLUMN_PATTERNS = [
    r"email", r"phone", r"mobile", r"address", r"ssn", r"salary", r"income",
    r"card", r"credit", r"password", r"secret", r"birth", r"dob", r"zip", r"postal",
    r"account", r"transaction", r"tax", r"ssn", r"passport", r"license"
]

def is_column_pii(column_name):
    col_lower = column_name.lower()
    for pattern in PII_COLUMN_PATTERNS:
        if re.search(pattern, col_lower):
            return True
    return False

def mask_sensitive_value(value, column_name):
    if value is None or pd.isna(value):
        return None
    val_str = str(value).strip()
    if not val_str:
        return val_str
    
    col_lower = column_name.lower()
    if "email" in col_lower:
        # Simple email mask
        parts = val_str.split("@")
        if len(parts) == 2:
            username, domain = parts
            masked_user = username[0] + "*" * (len(username) - 1) if len(username) > 1 else "*"
            return f"{masked_user}@{domain}"
        return "****@example.com"
    elif "phone" in col_lower or "mobile" in col_lower:
        return "****-****-" + val_str[-4:] if len(val_str) >= 4 else "**********"
    elif "card" in col_lower:
        return "****-****-****-" + val_str[-4:] if len(val_str) >= 4 else "****************"
    elif "password" in col_lower or "secret" in col_lower:
        return "********"
    elif "salary" in col_lower or "income" in col_lower or "tax" in col_lower:
        return "$XX,XXX"
    else:
        return "[MASKED_PII_DATA]"

def infer_column_type(series):
    # Check if series is mostly datetime
    if pd.api.types.is_datetime64_any_dtype(series):
        return "DATETIME"
    
    # Try converting to datetime if string
    if pd.api.types.is_string_dtype(series):
        # Sample non-nulls
        sample = series.dropna().head(100)
        if len(sample) > 0:
            try:
                pd.to_datetime(sample, format='mixed', errors='raise')
                # If conversion succeeded, double check format
                return "DATETIME"
            except:
                pass
                
    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    elif pd.api.types.is_float_dtype(series):
        return "FLOAT"
    elif pd.api.types.is_bool_dtype(series):
        return "BOOLEAN"
    else:
        return "TEXT"

def generate_df_metadata(df, table_name):
    """
    Computes statistical and structural metadata from a Pandas DataFrame
    """
    row_count = len(df)
    columns_metadata = []
    
    for col in df.columns:
        series = df[col]
        data_type = infer_column_type(series)
        
        null_count = int(series.isna().sum())
        distinct_count = int(series.nunique())
        
        # Min and Max calculations safely
        min_val = None
        max_val = None
        non_null_series = series.dropna()
        if len(non_null_series) > 0:
            try:
                min_val = str(non_null_series.min())
                max_val = str(non_null_series.max())
            except Exception:
                pass
        
        # Determine PII status
        is_pii = 1 if is_column_pii(col) else 0
        
        # Get sample values
        sample_series = non_null_series.head(5).tolist()
        sample_values = []
        for val in sample_series:
            # Handle float Nan/inf or complex objects
            if isinstance(val, (int, float, str, bool)):
                if is_pii == 1:
                    sample_values.append(mask_sensitive_value(val, col))
                else:
                    sample_values.append(val)
            else:
                sample_values.append(str(val))
        
        # Build health score metrics for column
        health_metrics = {
            "null_percentage": round((null_count / row_count * 100), 2) if row_count > 0 else 0,
            "uniqueness_ratio": round((distinct_count / row_count), 2) if row_count > 0 else 0,
            "duplicate_count": row_count - distinct_count if row_count > 0 else 0
        }
        
        columns_metadata.append({
            "column_name": col,
            "data_type": data_type,
            "sample_values": sample_values,
            "null_count": null_count,
            "distinct_count": distinct_count,
            "min_val": min_val,
            "max_val": max_val,
            "is_pii": is_pii,
            "health_metrics": health_metrics
        })
        
    return {
        "table_name": table_name,
        "row_count": row_count,
        "columns": columns_metadata
    }

def load_csv_metadata(file_path, table_name=None):
    if not table_name:
        table_name = os.path.splitext(os.path.basename(file_path))[0]
    
    df = pd.read_csv(file_path, nrows=5000) # Read up to 5000 rows for profiling speed
    return generate_df_metadata(df, table_name)

def load_json_metadata(file_path, table_name=None):
    if not table_name:
        table_name = os.path.splitext(os.path.basename(file_path))[0]
        
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # JSON Flattening
    if isinstance(data, list):
        df = pd.json_normalize(data)
    elif isinstance(data, dict):
        # Look for nested arrays
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
        raise ValueError("Invalid JSON format - must be dictionary or list of objects")
        
    return generate_df_metadata(df, table_name)

def load_sqlite_metadata(file_path):
    conn = sqlite3.connect(file_path)
    cursor = conn.cursor()
    
    try:
        # Get list of tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [row[0] for row in cursor.fetchall()]
        
        dataset_metadata = []
        for table in tables:
            # Get table count
            cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
            row_count = cursor.fetchone()[0]
            
            # Load row samples
            df = pd.read_sql_query(f"SELECT * FROM `{table}` LIMIT 2000", conn)
            table_meta = generate_df_metadata(df, table)
            table_meta["row_count"] = row_count # Override limit count with actual count
            dataset_metadata.append(table_meta)
            
        return dataset_metadata
    finally:
        conn.close()

def load_postgres_metadata(connection_uri):
    """
    Extracts metadata from a PostgreSQL database using SQLAlchemy.
    """
    engine = create_engine(connection_uri)
    inspector = inspect(engine)
    
    dataset_metadata = []
    try:
        tables = inspector.get_table_names()
        for table in tables:
            # Query Row Count
            row_count = 0
            try:
                with engine.connect() as conn:
                    res = conn.execute(f"SELECT COUNT(*) FROM \"{table}\"")
                    row_count = res.scalar()
            except Exception:
                pass
            
            # Load row samples for column stats and PII mapping
            try:
                df = pd.read_sql_query(f"SELECT * FROM \"{table}\" LIMIT 2000", engine)
                table_meta = generate_df_metadata(df, table)
            except Exception:
                # Fallback to catalog schema only if query fails
                columns = inspector.get_columns(table)
                table_meta = {
                    "table_name": table,
                    "row_count": row_count,
                    "columns": []
                }
                for col in columns:
                    col_name = col['name']
                    table_meta["columns"].append({
                        "column_name": col_name,
                        "data_type": str(col['type']),
                        "sample_values": [],
                        "null_count": 0,
                        "distinct_count": 0,
                        "min_val": None,
                        "max_val": None,
                        "is_pii": 1 if is_column_pii(col_name) else 0,
                        "health_metrics": {"null_percentage": 0, "uniqueness_ratio": 0, "duplicate_count": 0}
                    })
                    
            table_meta["row_count"] = row_count
            dataset_metadata.append(table_meta)
            
        return dataset_metadata
    finally:
        engine.dispose()
