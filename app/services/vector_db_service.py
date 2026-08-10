import chromadb
from typing import List, Dict, Any, Optional
from loguru import logger
from sqlalchemy.orm import Session
from ..config import get_settings

class VectorDBService:
    _instance = None
    _client = None
    _collection = None
    _db = None
    
    def __new__(cls, db: Session = None):
        if cls._instance is None:
            cls._instance = super(VectorDBService, cls).__new__(cls)
            cls._instance._db = db
            cls._instance.settings = get_settings(db)
            cls._instance._setup_client()
        elif db and db != cls._instance._db:
            # Update settings if a different database session is provided
            cls._instance._db = db
            cls._instance.settings = get_settings(db)
        return cls._instance
    
    @property
    def client(self):
        return self._client
    
    @property 
    def collection(self):
        return self._collection
    
    def _setup_client(self):
        """Setup ChromaDB client"""
        try:
            # Check if external ChromaDB server is configured
            if self.settings.chroma_host != "localhost" or self.settings.chroma_port != 8001:
                # Try to connect to external ChromaDB server
                try:
                    VectorDBService._client = chromadb.HttpClient(
                        host=self.settings.chroma_host,
                        port=self.settings.chroma_port
                    )
                    # Test connection
                    VectorDBService._client.heartbeat()
                    logger.info(f"Connected to ChromaDB server at {self.settings.chroma_host}:{self.settings.chroma_port}")
                except Exception as e:
                    logger.warning(f"Failed to connect to ChromaDB server: {e}")
                    raise
            else:
                # Use persistent client for local storage
                import os
                persist_directory = os.path.join(self.settings.data_dir, "chroma")
                os.makedirs(persist_directory, exist_ok=True)
                
                VectorDBService._client = chromadb.PersistentClient(
                    path=persist_directory
                )
                logger.info(f"Using persistent ChromaDB at: {persist_directory}")
                
            # Get or create collection
            try:
                VectorDBService._collection = VectorDBService._client.get_collection(
                    name=self.settings.chroma_collection_name
                )
                logger.info(f"Connected to existing collection: {self.settings.chroma_collection_name}")
            except Exception:
                VectorDBService._collection = VectorDBService._client.create_collection(
                    name=self.settings.chroma_collection_name,
                    metadata={"description": "Document embeddings for semantic search", "hnsw:space": "cosine"}
                )
                logger.info(f"Created new collection: {self.settings.chroma_collection_name}")
                
        except Exception as e:
            logger.warning(f"Failed to setup persistent ChromaDB: {e}")
            logger.info("Falling back to in-memory ChromaDB client")
            # Fallback to in-memory client
            VectorDBService._client = chromadb.Client()
            VectorDBService._collection = VectorDBService._client.get_or_create_collection(
                name=self.settings.chroma_collection_name,
                metadata={"description": "Document embeddings for semantic search", "hnsw:space": "cosine"}
            )
            logger.info(f"Created in-memory collection: {self.settings.chroma_collection_name}")
    
    @staticmethod
    def _is_dimension_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return "dimension" in text and ("match" in text or "expecting" in text)

    @staticmethod
    def _dimension_hint(exc: Exception) -> str:
        return (
            f"Embedding dimension mismatch: {exc}. The collection was built with a "
            "different embedding model. Re-index with: python cli.py reindex-vectors --force"
        )

    def add_document(self, document_id: str, text: str, embeddings: List[float], metadata: Dict[str, Any]):
        """Add a document to the vector database"""
        try:
            if self.collection is None:
                logger.warning("Vector DB collection is not initialized")
                return

            # upsert keeps re-indexing idempotent; add() raises on duplicate ids.
            if hasattr(self.collection, "upsert"):
                self.collection.upsert(
                    ids=[document_id],
                    embeddings=[embeddings],
                    documents=[text],
                    metadatas=[metadata],
                )
            else:  # pragma: no cover - very old ChromaDB
                self.collection.delete(ids=[document_id])
                self.collection.add(
                    ids=[document_id],
                    embeddings=[embeddings],
                    documents=[text],
                    metadatas=[metadata],
                )
            logger.debug(f"Added document to vector DB: {document_id}")

        except Exception as e:
            if self._is_dimension_error(e):
                message = self._dimension_hint(e)
                logger.error(message)
                raise RuntimeError(message) from e
            logger.error(f"Failed to add document to vector DB: {e}")
            raise
    
    def update_document(self, document_id: str, text: str, embeddings: List[float], metadata: Dict[str, Any]):
        """Update a document in the vector database"""
        try:
            if self.collection is None:
                logger.warning("Vector DB collection is not initialized")
                return
                
            # ChromaDB doesn't have direct update, so we delete and add
            self.delete_document(document_id)
            self.add_document(document_id, text, embeddings, metadata)
            logger.debug(f"Updated document in vector DB: {document_id}")
            
        except Exception as e:
            logger.error(f"Failed to update document in vector DB: {e}")
            raise
    
    def delete_document(self, document_id: str):
        """Delete a document from the vector database"""
        try:
            if self.collection is None:
                logger.warning("Vector DB collection is not initialized")
                return
                
            self.collection.delete(ids=[document_id])
            logger.debug(f"Deleted document from vector DB: {document_id}")
            
        except Exception as e:
            logger.warning(f"Failed to delete document from vector DB (may not exist): {e}")
    
    def search_similar(self, query_embeddings: List[float], limit: int = 10, 
                      filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Search for similar documents using vector similarity"""
        try:
            if self.collection is None:
                logger.warning("Vector DB collection is not initialized")
                return []
                
            # Prepare where clause for filtering
            where_clause = None
            if filters:
                where_clause = {}
                for key, value in filters.items():
                    if value is not None:
                        where_clause[key] = value
            
            results = self.collection.query(
                query_embeddings=[query_embeddings],
                n_results=limit,
                where=where_clause
            )
            
            # Format results
            documents = []
            if results['ids'] and results['ids'][0]:
                for i in range(len(results['ids'][0])):
                    distance = results['distances'][0][i] if results['distances'] else None
                    # Convert distance to similarity score (lower distance = higher similarity)
                    # ChromaDB cosine distance: 0 = identical, 2 = opposite
                    # Convert to 0-1 similarity score where 1 = most similar
                    if distance is not None:
                        # Normalize cosine distance (0-2) to similarity score (1-0)
                        score = max(0, 1 - (distance / 2.0))
                    else:
                        score = 0.0
                    
                    doc = {
                        'id': results['ids'][0][i],
                        'distance': distance,
                        'score': max(0, score),  # Ensure score is non-negative
                        'text': results['documents'][0][i] if results['documents'] else None,
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {}
                    }
                    documents.append(doc)
            
            logger.debug(f"Found {len(documents)} similar documents")
            return documents

        except Exception as e:
            if self._is_dimension_error(e):
                message = self._dimension_hint(e)
                logger.error(message)
                raise RuntimeError(message) from e
            logger.error(f"Failed to search similar documents: {e}")
            raise
    
    def search_by_text(self, query: str, limit: int = 10, 
                      filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Search documents by text query (using ChromaDB's built-in embedding)"""
        try:
            where_clause = None
            if filters:
                where_clause = {}
                for key, value in filters.items():
                    if value is not None:
                        where_clause[key] = value
            
            results = self.collection.query(
                query_texts=[query],
                n_results=limit,
                where=where_clause
            )
            
            # Format results
            documents = []
            if results['ids'] and results['ids'][0]:
                for i in range(len(results['ids'][0])):
                    doc = {
                        'id': results['ids'][0][i],
                        'distance': results['distances'][0][i] if results['distances'] else None,
                        'text': results['documents'][0][i] if results['documents'] else None,
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {}
                    }
                    documents.append(doc)
            
            logger.debug(f"Found {len(documents)} documents for text query")
            return documents
            
        except Exception as e:
            logger.error(f"Failed to search by text: {e}")
            raise
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the collection"""
        try:
            count = self.collection.count()
            return {
                "document_count": count,
                "collection_name": self.settings.chroma_collection_name
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {"document_count": 0, "collection_name": self.settings.chroma_collection_name}
    
    def reset_collection(self):
        """Reset (clear) the entire collection"""
        try:
            # Delete the collection
            VectorDBService._client.delete_collection(name=self.settings.chroma_collection_name)
            
            # Recreate it
            VectorDBService._collection = VectorDBService._client.create_collection(
                name=self.settings.chroma_collection_name,
                metadata={"description": "Document embeddings for semantic search", "hnsw:space": "cosine"}
            )
            
            logger.info(f"Reset collection: {self.settings.chroma_collection_name}")
            
        except Exception as e:
            logger.error(f"Failed to reset collection: {e}")
            raise
