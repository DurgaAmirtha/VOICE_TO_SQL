import chromadb
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple
from config import Config
from rag.schema_extractor import SchemaExtractor
from utils.common import logger

class HybridEmbeddingFunction(chromadb.EmbeddingFunction):
    _local_failed = True # Set to True to disable local SentenceTransformer (saves ~450MB RAM, preventing Render free-tier memory crashes)

    def __init__(self):
        self.local_model = None
        if HybridEmbeddingFunction._local_failed:
            logger.info("SentenceTransformer marked as failed. Bypassing local load.")
            return

        try:
            logger.info("Attempting to load local SentenceTransformer: all-MiniLM-L6-v2")
            from sentence_transformers import SentenceTransformer
            self.local_model = SentenceTransformer(Config.EMBEDDING_MODEL_NAME)
            logger.info("SentenceTransformer model loaded successfully.")
        except Exception as e:
            HybridEmbeddingFunction._local_failed = True
            logger.warning(
                f"Could not load local SentenceTransformer: {e}. "
                "Vector store will fallback to Google Gemini Embeddings API."
            )

    def __call__(self, input: chromadb.Documents) -> chromadb.Embeddings:
        # Try local model first
        if self.local_model is not None:
            try:
                embeddings = self.local_model.encode(input)
                return [arr.tolist() for arr in embeddings]
            except Exception as e:
                logger.error(f"Local embedding execution failed: {e}. Falling back to Gemini.")

        # Fallback to Gemini Embedding API
        try:
            from google import genai
            from google.genai import types
            api_key = Config.GEMINI_API_KEY
            if not api_key:
                raise ValueError("GEMINI_API_KEY is not set in environment variables.")
            
            client = genai.Client(api_key=api_key)
            logger.info(f"Generating embeddings via Gemini API (text-embedding-004) for {len(input)} docs...")
            
            response = client.models.embed_content(
                model="models/gemini-embedding-001",
                contents=input,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT"
                )
            )
            
            embeddings = []
            if response and response.embeddings:
                embeddings = [emb.values for emb in response.embeddings]
            return embeddings
        except Exception as api_err:
            logger.error(f"Gemini API embedding generation failed: {api_err}")
            raise api_err

class VectorStoreManager:
    _client = None
    _embedding_function = None

    @classmethod
    def get_client(cls) -> chromadb.PersistentClient:
        """Singleton pattern to initialize and cache the Chroma client."""
        if cls._client is None:
            logger.info(f"Initializing ChromaDB Persistent Client at {Config.CHROMA_DIR}")
            cls._client = chromadb.PersistentClient(path=str(Config.CHROMA_DIR))
        return cls._client

    @classmethod
    def get_embedding_function(cls) -> HybridEmbeddingFunction:
        """Singleton pattern for loading hybrid embedding function."""
        if cls._embedding_function is None:
            cls._embedding_function = HybridEmbeddingFunction()
        return cls._embedding_function

    @classmethod
    def index_database_schema(cls, db_path: str | Path) -> None:
        """
        Extracts schemas for all tables in the database, indexes them in ChromaDB,
        and saves them locally in a JSON cache for offline/keyless fallbacks.
        """
        db_path = Path(db_path).resolve()
        
        # Extract tables schema details
        schema_summary = SchemaExtractor.get_database_schema_summary(db_path)
        
        documents = []
        metadatas = []
        ids = []
        
        for table_name, table_meta in schema_summary.items():
            doc = SchemaExtractor.generate_schema_document(table_meta)
            doc_id = f"{db_path.name}_{table_name}"
            
            documents.append(doc)
            metadatas.append({
                "db_path": str(db_path),
                "table_name": table_name
            })
            ids.append(doc_id)
            
        # 1. Update local JSON schema cache (bulletproof offline fallback)
        try:
            cache_path = Path(Config.DATABASE_DIR) / "schema_cache.json"
            cache_data = {}
            if cache_path.exists():
                try:
                    with open(cache_path, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)
                except Exception:
                    pass
            
            db_key = str(db_path)
            cache_data[db_key] = []
            for doc, table_name in zip(documents, [m["table_name"] for m in metadatas]):
                cache_data[db_key].append({
                    "table_name": table_name,
                    "document": doc
                })
                
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=4)
            logger.info(f"Local JSON schema cache updated at {cache_path}")
        except Exception as json_err:
            logger.warning(f"Failed to write local JSON schema cache: {json_err}")

        # 2. Update ChromaDB
        if ids:
            try:
                client = cls.get_client()
                embed_fn = cls.get_embedding_function()
                collection = client.get_or_create_collection(
                    name=Config.CHROMA_SCHEMA_COLLECTION,
                    embedding_function=embed_fn
                )
                logger.info(f"Indexing {len(ids)} tables in ChromaDB for database: {db_path.name}")
                collection.upsert(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas
                )
                logger.info("ChromaDB indexing completed.")
            except Exception as chroma_err:
                logger.warning(f"ChromaDB indexing failed: {chroma_err}. Schema cached in local JSON instead.")
        else:
            logger.warning(f"No tables found to index for database: {db_path.name}")

    @classmethod
    def retrieve_relevant_schemas(cls, query: str, db_path: str | Path, top_n: int = 3) -> Tuple[List[str], List[str]]:
        """
        Queries table schemas relevant to the query. 
        Tries ChromaDB first, falling back to local JSON keyword overlap matching if it fails.
        """
        db_path = str(Path(db_path).resolve())
        retrieved_tables = []
        retrieved_docs = []
        
        chroma_success = False
        
        # 1. Attempt ChromaDB
        try:
            client = cls.get_client()
            embed_fn = cls.get_embedding_function()
            collection = client.get_collection(
                name=Config.CHROMA_SCHEMA_COLLECTION,
                embedding_function=embed_fn
            )
            
            logger.info(f"Querying ChromaDB for: '{query}' [DB: {Path(db_path).name}]")
            results = collection.query(
                query_texts=[query],
                n_results=top_n,
                where={"db_path": db_path}
            )
            
            if results and results["documents"] and results["documents"][0]:
                documents = results["documents"][0]
                metadatas = results["metadatas"][0]
                
                for doc, meta in zip(documents, metadatas):
                    retrieved_tables.append(meta["table_name"])
                    retrieved_docs.append(doc)
                chroma_success = True
                logger.info(f"ChromaDB retrieved tables: {retrieved_tables}")
        except Exception as chroma_err:
            logger.warning(f"ChromaDB retrieval failed/bypassed: {chroma_err}. Falling back to local JSON keyword matcher.")

        # 2. Local JSON Keyword overlap matcher fallback (runs if ChromaDB fails or has no key)
        if not chroma_success:
            try:
                cache_path = Path(Config.DATABASE_DIR) / "schema_cache.json"
                tables_list = []
                
                if cache_path.exists():
                    with open(cache_path, "r", encoding="utf-8") as f:
                        cache_data = json.load(f)
                    tables_list = cache_data.get(db_key := str(db_path), [])
                
                # If cache file doesn't exist or is empty, extract dynamically
                if not tables_list:
                    logger.info("Local schema cache missing. Generating schema dynamically...")
                    schema_summary = SchemaExtractor.get_database_schema_summary(Path(db_path))
                    for table_name, table_meta in schema_summary.items():
                        doc = SchemaExtractor.generate_schema_document(table_meta)
                        tables_list.append({
                            "table_name": table_name,
                            "document": doc
                        })
                
                # Simple and effective TF-IDF style keyword match scorer
                query_words = set(re.findall(r'\w+', query.lower()))
                scored_tables = []
                
                for item in tables_list:
                    table_name = item["table_name"]
                    doc = item["document"]
                    
                    doc_words = set(re.findall(r'\w+', doc.lower()))
                    overlap = len(query_words.intersection(doc_words))
                    
                    # Direct table name mention boost
                    if table_name.lower() in query.lower():
                        overlap += 10
                        
                    scored_tables.append((overlap, table_name, doc))
                
                # Sort descending
                scored_tables.sort(key=lambda x: x[0], reverse=True)
                
                for score, table_name, doc in scored_tables[:top_n]:
                    retrieved_tables.append(table_name)
                    retrieved_docs.append(doc)
                logger.info(f"Local JSON schema matcher retrieved: {retrieved_tables}")
            except Exception as local_err:
                logger.error(f"Local JSON keyword matcher failed: {local_err}")

        # 3. Final safety net: If no tables retrieved, fetch all tables from SQLite
        if not retrieved_tables:
            logger.warning("No table schemas retrieved. Querying all SQLite database tables as fallback.")
            try:
                from database.db_manager import DBManager
                active_tables = DBManager.get_table_names(db_path)
                schema_summary = SchemaExtractor.get_database_schema_summary(Path(db_path))
                
                for tbl in active_tables:
                    retrieved_tables.append(tbl)
                    if tbl in schema_summary:
                        retrieved_docs.append(SchemaExtractor.generate_schema_document(schema_summary[tbl]))
            except Exception as db_fallback_err:
                logger.error(f"Database catalog retrieval failed: {db_fallback_err}")

        return retrieved_tables, retrieved_docs
