"""Vector-based memory using ChromaDB for scalable RAG"""
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import logging
import os
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class VectorMemory:
    def __init__(self, collection_name: str = "research_memory", 
                 persist_directory: str = None):
        if persist_directory is None:
            # Використовуємо шлях відносно папки data
            base_dir = Path(__file__).parent.parent
            persist_directory = str(base_dir / "data" / "chromadb")
            
        os.makedirs(persist_directory, exist_ok=True)
        
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        # Використовуємо легку embedding-модель
        logger.info("Loading SentenceTransformer model 'all-MiniLM-L6-v2'...")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
    
    def add_text(self, text: str, metadata: Optional[Dict] = None, 
                 doc_id: Optional[str] = None) -> str:
        """Add text to vector memory"""
        if not text or not text.strip():
            return ""
            
        if not doc_id:
            import uuid
            doc_id = str(uuid.uuid4())
        
        embedding = self.embedder.encode(text).tolist()
        
        self.collection.add(
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata or {}],
            ids=[doc_id]
        )
        return doc_id
    
    def search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Search memory by semantic similarity"""
        if not query or not query.strip():
            return []
            
        query_embedding = self.embedder.encode(query).tolist()
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )
        
        documents = []
        if results and 'documents' in results and results['documents']:
            for i, doc in enumerate(results['documents'][0]):
                documents.append({
                    'content': doc,
                    'metadata': results['metadatas'][0][i] if 'metadatas' in results and results['metadatas'] else {},
                    'distance': results['distances'][0][i] if 'distances' in results and results['distances'] else None
                })
        return documents
    
    def search_hybrid(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Hybrid search combining Vector similarity and Keyword matching"""
        # 1. Векторний пошук
        vector_results = self.search(query, n_results=n_results)
        
        # 2. Ключовий пошук (через where фільтр ChromaDB, якщо можливо, 
        #    або просто фільтрація результатів)
        keywords = query.lower().split()
        if not keywords:
            return vector_results
            
        # Додаємо оцінку за ключові слова
        for res in vector_results:
            content_lower = res['content'].lower()
            keyword_matches = sum(1 for k in keywords if k in content_lower)
            res['keyword_score'] = keyword_matches / len(keywords)
            
            # Підвищуємо релевантність якщо є збіги за ключами
            if 'distance' in res and res['distance'] is not None:
                # Косинусна відстань: менше = краще. Зменшуємо відстань за ключові слова.
                res['distance'] -= (res['keyword_score'] * 0.1)
        
        # Сортуємо за оновленою відстанню
        vector_results.sort(key=lambda x: x.get('distance', 1.0))
        return vector_results

    def get_all_context(self, query: str, max_chars: int = 5000) -> str:
        """Get formatted context from memory for LLM prompt"""
        results = self.search(query)
        context_parts = []
        total_chars = 0
        
        for r in results:
            if total_chars + len(r['content']) > max_chars:
                break
            context_parts.append(r['content'])
            total_chars += len(r['content'])
        
        return "\n\n".join(context_parts) if context_parts else ""
