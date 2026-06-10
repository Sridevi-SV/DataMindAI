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

def index_catalog(dataset_id, tables_metadata, relationships=None, glossary_terms=None):
    """
    Saves and indexes table definitions, columns, relationships and business terms.
    """
    documents = []
    metadatas = []
    ids = []
    
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
                "term_name": tname
            })
            ids.append(f"glossary_{tname}")
            
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

def retrieve_context(query, top_k=5):
    """
    Performs search over the catalog.
    """
    client = get_chroma_client()
    model = get_embedding_model()
    
    if client and model and CHROMA_AVAILABLE:
        try:
            collection = client.get_collection(name="datamind_catalog")
            query_vector = model.encode([query]).tolist()[0]
            results = collection.query(
                query_embeddings=[query_vector],
                n_results=top_k
            )
        except Exception:
            # Fall back to local search if query throws exception
            results = _local_search_db.query(query, top_k)
    else:
        results = _local_search_db.query(query, top_k)
        
    formatted_results = []
    if results and "documents" in results and results["documents"]:
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0] if "distances" in results else [0.0]*len(docs)
        
        for i in range(len(docs)):
            formatted_results.append({
                "document": docs[i],
                "metadata": metas[i],
                "distance": distances[i]
            })
            
    return formatted_results

def pii_flag_text(is_pii):
    return "Sensitive PII (Masked)" if is_pii == 1 else "Non-PII (Standard)"
