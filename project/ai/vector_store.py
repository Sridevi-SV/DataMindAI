import os
import re

# Fallback in-memory search engine if chromadb or sentence-transformers fail to import due to local protobuf conflicts
class LocalSearchEngine:
    def __init__(self):
        self.documents = []
        self.metadatas = []
        self.ids = []
        
    def add_documents(self, ids, documents, metadatas):
        for i, doc_id in enumerate(ids):
            if doc_id in self.ids:
                idx = self.ids.index(doc_id)
                self.documents[idx] = documents[i]
                self.metadatas[idx] = metadatas[i]
            else:
                self.ids.append(doc_id)
                self.documents.append(documents[i])
                self.metadatas.append(metadatas[i])
                
    def query(self, query_text, top_k=5):
        query_words = set(re.findall(r'\w+', query_text.lower()))
        if not query_words:
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}
            
        scores = []
        for idx, doc in enumerate(self.documents):
            doc_words = re.findall(r'\w+', doc.lower())
            doc_word_set = set(doc_words)
            
            # Calculate intersection overlap
            intersection = query_words.intersection(doc_word_set)
            score = len(intersection) / len(query_words) if len(query_words) > 0 else 0.0
            
            # Boost score for exact match substrings
            for word in query_words:
                if word in doc.lower():
                    score += 0.2
            
            scores.append((score, idx))
            
        scores.sort(key=lambda x: x[0], reverse=True)
        
        results = {"documents": [[]], "metadatas": [[]], "distances": [[]]}
        for score, idx in scores[:top_k]:
            results["documents"][0].append(self.documents[idx])
            results["metadatas"][0].append(self.metadatas[idx])
            results["distances"][0].append(round(1.0 - score, 3))
            
        return results

# Shared in-memory search instance
_local_search_db = LocalSearchEngine()

# Try to load deep learning packages, degrade gracefully if conflicts exist
CHROMA_AVAILABLE = False
try:
    import chromadb
    from sentence_transformers import SentenceTransformer
    CHROMA_AVAILABLE = True
except Exception as e:
    print(f"Warning: Offline sentence-transformers or ChromaDB unavailable ({type(e).__name__}). Falling back to pure Python LocalSearchEngine.")

CHROMA_PATH = os.getenv("CHROMA_DB_PATH", "./data/chromadb")
EMBEDDING_MODEL_NAME = 'all-MiniLM-L6-v2'

_embedding_model = None

def get_embedding_model():
    global _embedding_model, CHROMA_AVAILABLE
    if not CHROMA_AVAILABLE:
        return None
    if _embedding_model is None:
        try:
            _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        except Exception:
            CHROMA_AVAILABLE = False
            return None
    return _embedding_model

def get_chroma_client():
    if not CHROMA_AVAILABLE:
        return None
    if not os.path.exists(CHROMA_PATH):
        os.makedirs(CHROMA_PATH, exist_ok=True)
    try:
        return chromadb.PersistentClient(path=CHROMA_PATH)
    except Exception:
        return None

def clear_vector_store():
    global _local_search_db
    _local_search_db = LocalSearchEngine()
    
    client = get_chroma_client()
    if client and CHROMA_AVAILABLE:
        try:
            client.delete_collection(name="datamind_catalog")
            print("[VECTOR STORE] ChromaDB collection deleted successfully.")
        except Exception as e:
            print(f"[VECTOR STORE] ChromaDB collection deletion warning: {e}")

def index_catalog(dataset_id, tables_metadata, relationships=None, glossary_terms=None):
    """
    Saves and indexes table definitions, columns, relationships and business terms.
    Wipes out any old embeddings first to guarantee zero cross-dataset leakage.
    """
    clear_vector_store()
    
    documents = []
    metadatas = []
    ids = []
    
    # Standardize dataset_id to int
    try:
        dataset_id = int(dataset_id)
    except (ValueError, TypeError):
        pass
    
    # 1. Index Tables and Columns
    for table in tables_metadata:
        tname = table["table_name"]
        tdesc = table.get("description", "")
        
        column_names = [col["column_name"] for col in table["columns"]]
        col_list_str = ", ".join(column_names)
        
        table_doc = f"Table Name: {tname}\nDescription: {tdesc}\nColumns: {col_list_str}"
        documents.append(table_doc)
        metadatas.append({
            "type": "table",
            "dataset_id": dataset_id,
            "table_name": tname,
            "description": tdesc
        })
        ids.append(f"ds_{dataset_id}_tbl_{tname}")
        
        for col in table["columns"]:
            cname = col["column_name"]
            ctype = col["data_type"]
            cdesc = col.get("description", "")
            
            col_doc = (
                f"Column Name: {cname}\n"
                f"Table: {tname}\n"
                f"Data Type: {ctype}\n"
                f"Privacy: {pii_flag_text(col.get('is_pii', 0))}\n"
                f"Description: {cdesc}"
            )
            documents.append(col_doc)
            metadatas.append({
                "type": "column",
                "dataset_id": dataset_id,
                "table_name": tname,
                "column_name": cname,
                "data_type": ctype,
                "is_pii": col.get("is_pii", 0)
            })
            ids.append(f"ds_{dataset_id}_col_{tname}_{cname}")
            
    # 2. Index Relationships
    if relationships:
        for idx, rel in enumerate(relationships):
            rel_doc = (
                f"Relationship: Table {rel['source_table']} links to {rel['target_table']} "
                f"on keys ({rel['source_column']} -> {rel['target_column']}). "
                f"Confidence: {rel['confidence']}. Type: {rel['type']}. "
                f"Details: {rel['details'].get('reason', '')}"
            )
            documents.append(rel_doc)
            metadatas.append({
                "type": "relationship",
                "dataset_id": dataset_id,
                "source_table": rel["source_table"],
                "target_table": rel["target_table"]
            })
            ids.append(f"ds_{dataset_id}_rel_{idx}")
            
    # 3. Index Glossary Terms
    if glossary_terms:
        for term in glossary_terms:
            tname = term["term"]
            g_doc = (
                f"Glossary Term: {tname}\n"
                f"Definition: {term['definition']}\n"
                f"Business Meaning: {term['business_meaning']}\n"
                f"Usage Context: {term['business_usage']}"
            )
            documents.append(g_doc)
            metadatas.append({
                "type": "glossary",
                "dataset_id": dataset_id,
                "term_name": tname
            })
            ids.append(f"ds_{dataset_id}_glossary_{tname}")
            
    # Add to the active storage index
    if documents:
        # Add to local engine first
        _local_search_db.add_documents(ids, documents, metadatas)
        
        # Add to Chroma if available
        client = get_chroma_client()
        model = get_embedding_model()
        
        if client and model and CHROMA_AVAILABLE:
            try:
                collection = client.get_or_create_collection(name="datamind_catalog")
                embeddings = model.encode(documents).tolist()
                collection.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas
                )
                print(f"ChromaDB: Indexed {len(documents)} elements for dataset {dataset_id}")
            except Exception as e:
                print(f"Warning: ChromaDB write failed ({str(e)}). Using local in-memory index.")
        else:
            print(f"LocalSearchEngine: Indexed {len(documents)} elements in memory.")

def retrieve_context(query, dataset_id=None, top_k=5):
    """
    Performs search over the catalog, strictly filtering by dataset_id.
    """
    client = get_chroma_client()
    model = get_embedding_model()
    
    # Standardize dataset_id to int if present
    if dataset_id is not None:
        try:
            dataset_id = int(dataset_id)
        except ValueError:
            pass

    if client and model and CHROMA_AVAILABLE:
        try:
            collection = client.get_collection(name="datamind_catalog")
            query_vector = model.encode([query]).tolist()[0]
            
            kwargs = {}
            if dataset_id is not None:
                kwargs["where"] = {"dataset_id": dataset_id}
                
            results = collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                **kwargs
            )
        except Exception:
            results = _local_search_db.query(query, top_k)
    else:
        results = _local_search_db.query(query, top_k)
        
    formatted_results = []
    if results and "documents" in results and results["documents"]:
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0] if "distances" in results else [0.0]*len(docs)
        
        for i in range(len(docs)):
            # Double check filtering on dataset_id for local search fallback
            meta_ds_id = metas[i].get("dataset_id")
            if dataset_id is not None:
                try:
                    meta_ds_id = int(meta_ds_id)
                except (ValueError, TypeError):
                    pass
                if meta_ds_id != dataset_id:
                    continue
                    
            formatted_results.append({
                "document": docs[i],
                "metadata": metas[i],
                "distance": distances[i]
            })
            
    return formatted_results

def rebuild_vector_store(dataset_id):
    """
    Rebuilds vector store embeddings from SQLite metadata database for the given dataset_id,
    clearing all previous documents.
    """
    import json
    from backend.database import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. Load Tables and columns
        cursor.execute("SELECT id, name, description, row_count FROM tables WHERE dataset_id = ?", (dataset_id,))
        table_rows = [dict(r) for r in cursor.fetchall()]
        
        tables_metadata = []
        for row in table_rows:
            table_id = row.get("id")
            tname = row.get("name") or row.get("table_name")
            tdesc = row.get("description") or ""
            row_count = row.get("row_count") or 0
            
            # Fetch columns for this table
            cursor.execute("SELECT name, data_type, description, is_pii FROM columns WHERE table_id = ?", (table_id,))
            col_rows = [dict(r) for r in cursor.fetchall()]
            
            columns = []
            for col_row in col_rows:
                cname = col_row.get("name") or col_row.get("column_name")
                ctype = col_row.get("data_type") or "TEXT"
                cdesc = col_row.get("description") or ""
                is_pii = col_row.get("is_pii") or 0
                columns.append({
                    "column_name": cname,
                    "data_type": ctype,
                    "description": cdesc,
                    "is_pii": is_pii
                })
                
            tables_metadata.append({
                "table_name": tname,
                "description": tdesc,
                "row_count": row_count,
                "columns": columns
            })
            
        # 2. Load Relationships
        cursor.execute("SELECT source_table, source_column, target_table, target_column, confidence, type, details_json FROM relationships WHERE dataset_id = ?", (dataset_id,))
        rel_rows = [dict(r) for r in cursor.fetchall()]
        relationships = []
        for row in rel_rows:
            source_table = row.get("source_table")
            source_column = row.get("source_column")
            target_table = row.get("target_table")
            target_column = row.get("target_column")
            confidence = row.get("confidence") or 0.0
            rel_type = row.get("type") or "one-to-many"
            details_json = row.get("details_json")
            try:
                details = json.loads(details_json) if details_json else {}
            except Exception:
                details = {}
            relationships.append({
                "source_table": source_table,
                "source_column": source_column,
                "target_table": target_table,
                "target_column": target_column,
                "confidence": confidence,
                "type": rel_type,
                "details": details
            })
            
        # 3. Load Glossary Terms
        cursor.execute("SELECT term, definition, business_meaning, business_usage, example_val FROM glossary")
        glossary_rows = [dict(r) for r in cursor.fetchall()]
        glossary_terms = []
        for row in glossary_rows:
            term = row.get("term")
            definition = row.get("definition") or ""
            business_meaning = row.get("business_meaning") or ""
            business_usage = row.get("business_usage") or ""
            example_val = row.get("example_val") or ""
            glossary_terms.append({
                "term": term,
                "definition": definition,
                "business_meaning": business_meaning,
                "business_usage": business_usage,
                "example_val": example_val
            })
            
        # Index in catalog
        index_catalog(
            dataset_id=dataset_id,
            tables_metadata=tables_metadata,
            relationships=relationships,
            glossary_terms=glossary_terms
        )
        print(f"[VECTOR STORE] Rebuilt embeddings for dataset_id {dataset_id}")
    finally:
        conn.close()

def pii_flag_text(is_pii):
    return "Sensitive PII (Masked)" if is_pii == 1 else "Non-PII (Standard)"
