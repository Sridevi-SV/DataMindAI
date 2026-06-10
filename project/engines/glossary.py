import sqlite3
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
            "flag" in name
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
