import json
import sqlite3
from datetime import datetime
from backend.database import get_db_connection, add_glossary_term, get_glossary_terms

def save_glossary_term(term, definition, business_meaning, business_usage, example_val):
    add_glossary_term(term, definition, business_meaning, business_usage, str(example_val))

def auto_generate_glossary_suggestions(columns_metadata):
    """
    Identifies candidate fields for glossary addition from column metadata (e.g. status, type, rate, total fields).
    """
    suggestions = []
    seen_terms = set()
    
    for col in columns_metadata:
        name = col["column_name"].lower()
        if name in seen_terms:
            continue
            
        # Select columns that look like key domain concepts
        is_candidate = (
            "status" in name or
            "type" in name or
            "category" in name or
            "channel" in name or
            "amount" in name or
            "price" in name or
            "revenue" in name or
            "score" in name or
            "cost" in name or
            "flag" in name or
            "gender" in name or
            "role" in name or
            "dept" in name or
            "department" in name or
            "level" in name or
            "rate" in name or
            "satisfaction" in name or
            "field" in name or
            "education" in name or
            "travel" in name or
            "income" in name or
            "year" in name or
            "age" in name or
            "performance" in name or
            "balance" in name or
            "marital" in name or
            "churn" in name or
            "tenure" in name or
            "partner" in name or
            "dependent" in name or
            "phone" in name or
            "contract" in name or
            "method" in name or
            "billing" in name or
            "charge" in name or
            "salary" in name or
            "time" in name or
            "distance" in name or
            "attrition" in name
        )
        
        if is_candidate:
            seen_terms.add(name)
            # Create a basic template definition
            suggestions.append({
                "term": col["column_name"].upper(),
                "data_type": col["data_type"],
                "definition": f"Standardized classifier column containing {col['column_name']} values.",
                "business_meaning": f"Used to categorize or track the state of {col['column_name'].replace('_', ' ')} in operational flows.",
                "business_usage": f"Reporting aggregations, filter segments, and data-cube slices.",
                "example_val": str(col["sample_values"][0]) if col["sample_values"] else "N/A"
            })
            
    return suggestions

def repopulate_glossary_from_db():
    """
    Back-populates business glossary definitions from existing columns in the database.
    Runs once on module import to ensure existing datasets are populated.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if column catalog is empty
        cursor.execute("SELECT COUNT(*) FROM columns")
        if cursor.fetchone()[0] == 0:
            return
            
        cursor.execute("""
            SELECT c.name as column_name, c.data_type, c.sample_values_json
            FROM columns c
        """)
        rows = cursor.fetchall()
        cols_meta = []
        for r in rows:
            try:
                samples = json.loads(r["sample_values_json"]) if r["sample_values_json"] else []
            except Exception:
                samples = []
            cols_meta.append({
                "column_name": r["column_name"],
                "data_type": r["data_type"],
                "sample_values": samples
            })
            
        suggestions = auto_generate_glossary_suggestions(cols_meta)
        for term_sug in suggestions:
            cursor.execute(
                """INSERT OR IGNORE INTO glossary 
                   (term, definition, business_meaning, business_usage, example_val, created_at) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    term_sug["term"], 
                    term_sug["definition"], 
                    term_sug["business_meaning"], 
                    term_sug["business_usage"], 
                    term_sug["example_val"], 
                    datetime.now().isoformat()
                )
            )
        conn.commit()
    except Exception as e:
        print(f"[GLOSSARY] Error repopulating glossary: {e}")
    finally:
        conn.close()

# Execute repopulation on startup
repopulate_glossary_from_db()
