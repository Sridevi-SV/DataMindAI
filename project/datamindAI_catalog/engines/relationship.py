import re
import json
import networkx as nx
import pandas as pd
import sqlite3
from sqlalchemy import create_engine

def discover_relationships(dataset_type, dataset_path, tables_metadata):
    """
    Analyzes the tables and columns to discover relationships.
    Uses naming patterns and optional local sample value overlaps to compute confidence scores.
    """
    relationships = []
    
    # Identify candidates using column names (e.g. ending in _id, _key, _code)
    id_columns = {}
    for table_idx, table in enumerate(tables_metadata):
        table_name = table["table_name"]
        id_columns[table_name] = []
        for col in table["columns"]:
            col_name = col["column_name"]
            is_pk = col["health_metrics"].get("uniqueness_ratio", 0) > 0.9 and col["null_count"] == 0
            
            # Match standard ID patterns
            is_id_candidate = (
                col_name.lower().endswith("_id") or 
                col_name.lower().endswith("id") or
                col_name.lower().endswith("_key") or 
                col_name.lower().endswith("key") or
                col_name.lower().endswith("_code") or
                col_name.lower() in ["id", "uuid", "uid", "code"]
            )
            
            if is_id_candidate or is_pk:
                id_columns[table_name].append({
                    "column_name": col_name,
                    "is_pk": is_pk,
                    "distinct_count": col["distinct_count"],
                    "data_type": col["data_type"]
                })
                
    # Compare candidate columns across tables
    table_names = list(id_columns.keys())
    for i in range(len(table_names)):
        for j in range(i + 1, len(table_names)):
            t1 = table_names[i]
            t2 = table_names[j]
            
            for col1 in id_columns[t1]:
                for col2 in id_columns[t2]:
                    # Match clean names
                    name1_clean = re.sub(r'^(tbl_|t_)', '', col1["column_name"].lower())
                    name2_clean = re.sub(r'^(tbl_|t_)', '', col2["column_name"].lower())
                    
                    # If names match or one is a suffix of the other (e.g., customer_id and id)
                    names_match = (
                        name1_clean == name2_clean or 
                        (name1_clean.endswith(name2_clean) and len(name2_clean) > 2) or
                        (name2_clean.endswith(name1_clean) and len(name1_clean) > 2)
                    )
                    
                    if names_match and col1["data_type"] == col2["data_type"]:
                        # Calculate baseline confidence from names
                        confidence = 0.5
                        if name1_clean == name2_clean:
                            confidence += 0.2
                            
                        # If one of them is marked as primary key (highly unique)
                        if col1["is_pk"] or col2["is_pk"]:
                            confidence += 0.15
                            
                        # Try to compute value overlap percentage locally (if data source is available)
                        overlap_percentage = 0.0
                        try:
                            overlap_percentage = compute_local_overlap(
                                dataset_type, dataset_path, 
                                t1, col1["column_name"], 
                                t2, col2["column_name"]
                            )
                            # Update confidence based on overlap
                            if overlap_percentage > 0.8:
                                confidence += 0.2
                            elif overlap_percentage > 0.3:
                                confidence += 0.1
                            elif overlap_percentage == 0:
                                confidence -= 0.3
                        except Exception as e:
                            # If overlap check fails (e.g. data missing), keep schema-based confidence
                            overlap_percentage = 0.5 # assumed partial overlap
                            
                        confidence = min(max(confidence, 0.0), 1.0)
                        
                        if confidence >= 0.4:
                            # Determine relationship direction & type
                            # If col1 is highly unique (PK) and col2 is not, it's 1-to-many (t1 -> t2)
                            is_t1_unique = col1["is_pk"] or col1["distinct_count"] >= 0.95 * col2["distinct_count"]
                            is_t2_unique = col2["is_pk"] or col2["distinct_count"] >= 0.95 * col1["distinct_count"]
                            
                            rel_type = "many-to-many"
                            if is_t1_unique and is_t2_unique:
                                rel_type = "one-to-one"
                            elif is_t1_unique:
                                rel_type = "one-to-many" # t1 has unique key, t2 has foreign keys
                            elif is_t2_unique:
                                rel_type = "many-to-one" # t1 has foreign keys, t2 has unique key
                            
                            # Standardize direction as PK table to FK table
                            source_tbl, source_col = (t1, col1["column_name"]) if is_t1_unique or not is_t2_unique else (t2, col2["column_name"])
                            target_tbl, target_col = (t2, col2["column_name"]) if is_t1_unique or not is_t2_unique else (t1, col1["column_name"])
                            
                            join_suggestion = f"SELECT * FROM {source_tbl} JOIN {target_tbl} ON {source_tbl}.{source_col} = {target_tbl}.{target_col}"
                            
                            relationships.append({
                                "source_table": source_tbl,
                                "source_column": source_col,
                                "target_table": target_tbl,
                                "target_column": target_col,
                                "confidence": round(confidence, 2),
                                "type": rel_type,
                                "details": {
                                    "overlap_percentage": round(overlap_percentage, 2),
                                    "join_suggestion": join_suggestion,
                                    "reason": f"Matched by column names '{col1['column_name']}' / '{col2['column_name']}' with estimated {int(overlap_percentage*100)}% value overlap."
                                }
                            })
                            
    return relationships

def compute_local_overlap(ds_type, ds_path, t1, col1, t2, col2):
    """
    Loads columns from datasets locally and computes value intersection.
    Does NOT send raw data to LLM.
    """
    if not ds_path or not os.path.exists(ds_path):
        return 0.0
        
    s1 = set()
    s2 = set()
    
    if ds_type.upper() == 'SQLITE':
        conn = sqlite3.connect(ds_path)
        try:
            df1 = pd.read_sql_query(f"SELECT DISTINCT `{col1}` FROM `{t1}` WHERE `{col1}` IS NOT NULL LIMIT 1000", conn)
            df2 = pd.read_sql_query(f"SELECT DISTINCT `{col2}` FROM `{t2}` WHERE `{col2}` IS NOT NULL LIMIT 1000", conn)
            s1 = set(df1[col1].dropna().tolist())
            s2 = set(df2[col2].dropna().tolist())
        finally:
            conn.close()
            
    elif ds_type.upper() == 'CSV':
        # CSV stands for a single table. If we have multiple tables in a folder, ds_path is the folder.
        # But if the file is just one csv, there are no other tables.
        # Let's assume folder structure
        if os.path.isdir(ds_path):
            path1 = os.path.join(ds_path, f"{t1}.csv")
            path2 = os.path.join(ds_path, f"{t2}.csv")
            if os.path.exists(path1) and os.path.exists(path2):
                df1 = pd.read_csv(path1, usecols=[col1], nrows=2000)
                df2 = pd.read_csv(path2, usecols=[col2], nrows=2000)
                s1 = set(df1[col1].dropna().unique().tolist())
                s2 = set(df2[col2].dropna().unique().tolist())
                
    elif ds_type.upper() == 'JSON':
        # JSON folder structure
        if os.path.isdir(ds_path):
            path1 = os.path.join(ds_path, f"{t1}.json")
            path2 = os.path.join(ds_path, f"{t2}.json")
            if os.path.exists(path1) and os.path.exists(path2):
                df1 = pd.json_normalize(json.load(open(path1)))
                df2 = pd.json_normalize(json.load(open(path2)))
                if col1 in df1.columns and col2 in df2.columns:
                    s1 = set(df1[col1].dropna().unique().tolist())
                    s2 = set(df2[col2].dropna().unique().tolist())
                    
    if not s1 or not s2:
        return 0.0
        
    intersection = s1.intersection(s2)
    # Overlap percent = intersection relative to the smaller set
    min_len = min(len(s1), len(s2))
    return len(intersection) / min_len if min_len > 0 else 0.0

def build_relationship_graph(relationships):
    """
    Constructs a NetworkX graph from relationship list.
    """
    G = nx.DiGraph()
    for rel in relationships:
        s = rel["source_table"]
        t = rel["target_table"]
        G.add_edge(
            s, t, 
            source_col=rel["source_column"], 
            target_col=rel["target_column"], 
            confidence=rel["confidence"],
            type=rel["type"]
        )
    return G
