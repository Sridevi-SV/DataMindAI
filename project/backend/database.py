import os
import sqlite3
import json
from datetime import datetime
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("METADATA_DB_PATH", "./data/metadata_catalog.db")

def get_db_connection():
    # Ensure directory exists
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Datasets Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS datasets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        type TEXT, -- 'CSV', 'JSON', 'SQLite', 'PostgreSQL'
        file_path TEXT,
        row_count INTEGER DEFAULT 0,
        uploaded_at TEXT
    )
    """)
    
    # 2. Tables Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dataset_id INTEGER,
        name TEXT,
        row_count INTEGER DEFAULT 0,
        description TEXT,
        columns_json TEXT, -- Cached columns list
        raw_schema_json TEXT,
        FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
        UNIQUE(dataset_id, name)
    )
    """)
    
    # 3. Columns Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS columns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_id INTEGER,
        name TEXT,
        data_type TEXT,
        sample_values_json TEXT,
        null_count INTEGER DEFAULT 0,
        distinct_count INTEGER DEFAULT 0,
        min_val TEXT,
        max_val TEXT,
        description TEXT,
        is_pii INTEGER DEFAULT 0,
        health_metrics_json TEXT,
        FOREIGN KEY (table_id) REFERENCES tables(id) ON DELETE CASCADE,
        UNIQUE(table_id, name)
    )
    """)
    
    # 4. Relationships Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS relationships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dataset_id INTEGER,
        source_table TEXT,
        source_column TEXT,
        target_table TEXT,
        target_column TEXT,
        confidence REAL DEFAULT 0.0,
        type TEXT, -- 'one-to-one', 'one-to-many', 'many-to-many'
        details_json TEXT,
        FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
    )
    """)
    
    # 5. Data Quality Metrics Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS quality_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dataset_id INTEGER,
        table_name TEXT,
        health_score REAL DEFAULT 100.0,
        missing_count INTEGER DEFAULT 0,
        duplicate_count INTEGER DEFAULT 0,
        outlier_count INTEGER DEFAULT 0,
        invalid_format_count INTEGER DEFAULT 0,
        details_json TEXT,
        recommendations_json TEXT,
        FOREIGN KEY (dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
        UNIQUE(dataset_id, table_name)
    )
    """)
    
    # 6. Business Glossary Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS glossary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        term TEXT UNIQUE,
        definition TEXT,
        business_meaning TEXT,
        business_usage TEXT,
        example_val TEXT,
        created_at TEXT
    )
    """)
    
    # 7. Agent Trace Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT,
        intent TEXT,
        plan_json TEXT,
        tools_used_json TEXT,
        context_retrieved_json TEXT,
        validation_status TEXT,
        response TEXT,
        latency_ms INTEGER,
        timestamp TEXT,
        model_used TEXT
    )
    """)
    
    conn.commit()
    conn.close()

# Helper CRUD operations for the application
def add_dataset(name, dst_type, file_path, row_count):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO datasets (name, type, file_path, row_count, uploaded_at) VALUES (?, ?, ?, ?, ?)",
            (name, dst_type, file_path, row_count, datetime.now().isoformat())
        )
        dataset_id = cursor.lastrowid
        if not dataset_id:
            cursor.execute("SELECT id FROM datasets WHERE name = ?", (name,))
            dataset_id = cursor.fetchone()[0]
        conn.commit()
        return dataset_id
    finally:
        conn.close()

def add_table(dataset_id, name, row_count, description, columns_json, raw_schema_json):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO tables (dataset_id, name, row_count, description, columns_json, raw_schema_json) VALUES (?, ?, ?, ?, ?, ?)",
            (dataset_id, name, row_count, description, columns_json, raw_schema_json)
        )
        table_id = cursor.lastrowid
        if not table_id:
            cursor.execute("SELECT id FROM tables WHERE dataset_id = ? AND name = ?", (dataset_id, name))
            table_id = cursor.fetchone()[0]
        conn.commit()
        return table_id
    finally:
        conn.close()

def add_column(table_id, name, data_type, sample_values_json, null_count, distinct_count, min_val, max_val, description, is_pii=0, health_metrics_json="{}"):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT OR REPLACE INTO columns 
               (table_id, name, data_type, sample_values_json, null_count, distinct_count, min_val, max_val, description, is_pii, health_metrics_json) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (table_id, name, data_type, sample_values_json, null_count, distinct_count, min_val, max_val, description, is_pii, health_metrics_json)
        )
        conn.commit()
    finally:
        conn.close()

def add_relationship(dataset_id, source_table, source_column, target_table, target_column, confidence, rel_type, details_json):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO relationships 
               (dataset_id, source_table, source_column, target_table, target_column, confidence, type, details_json) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (dataset_id, source_table, source_column, target_table, target_column, confidence, rel_type, details_json)
        )
        conn.commit()
    finally:
        conn.close()

def add_quality_metrics(dataset_id, table_name, health_score, missing_count, duplicate_count, outlier_count, invalid_format_count, details_json, recommendations_json):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT OR REPLACE INTO quality_metrics 
               (dataset_id, table_name, health_score, missing_count, duplicate_count, outlier_count, invalid_format_count, details_json, recommendations_json) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (dataset_id, table_name, health_score, missing_count, duplicate_count, outlier_count, invalid_format_count, details_json, recommendations_json)
        )
        conn.commit()
    finally:
        conn.close()

def add_glossary_term(term, definition, business_meaning, business_usage, example_val):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT OR REPLACE INTO glossary 
               (term, definition, business_meaning, business_usage, example_val, created_at) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (term, definition, business_meaning, business_usage, example_val, datetime.now().isoformat())
        )
        conn.commit()
    finally:
        conn.close()

def add_agent_log(question, intent, plan, tools_used, context_retrieved, validation_status, response, latency_ms, model_used):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO agent_logs 
               (question, intent, plan_json, tools_used_json, context_retrieved_json, validation_status, response, latency_ms, timestamp, model_used) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                question, 
                intent, 
                json.dumps(plan), 
                json.dumps(tools_used), 
                json.dumps(context_retrieved), 
                validation_status, 
                response, 
                latency_ms, 
                datetime.now().isoformat(),
                model_used
            )
        )
        conn.commit()
    finally:
        conn.close()

def get_glossary_terms(query=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if query:
            cursor.execute(
                "SELECT * FROM glossary WHERE term LIKE ? OR definition LIKE ? OR business_meaning LIKE ? ORDER BY term ASC",
                (f"%{query}%", f"%{query}%", f"%{query}%")
            )
        else:
            cursor.execute("SELECT * FROM glossary ORDER BY term ASC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

# Initialize tables when database module is first run
init_db()
print(f"Database initialized at: {DB_PATH}")

