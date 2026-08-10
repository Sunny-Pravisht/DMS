from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import SearchRequest, SearchResult, RAGRequest, RAGResponse
from ..services.search_service import SearchService
from ..models import User
from ..services.auth_service import require_permission_flexible

router = APIRouter()

@router.post("/", response_model=SearchResult)
def search_documents(
    search_request: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Search documents using full-text and/or semantic search"""
    search_service = SearchService(db)
    return search_service.search_documents(search_request, db)

@router.get("/suggestions")
def get_search_suggestions(
    q: str = Query(..., min_length=2, description="Partial query for suggestions"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Get search suggestions based on partial query"""
    search_service = SearchService(db)
    return search_service.get_search_suggestions(q, db)

@router.post("/rag", response_model=RAGResponse)
def rag_query(
    rag_request: RAGRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Answer questions using RAG (Retrieval-Augmented Generation)"""
    search_service = SearchService(db)
    return search_service.rag_query(rag_request, db)

@router.get("/test-semantic")
def test_semantic_search(
    query: str = Query(..., description="Test query for semantic search"),
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Test endpoint for semantic search functionality"""
    try:
        # Create a simple search request
        search_request = SearchRequest(
            query=query,
            limit=limit,
            use_semantic_search=True
        )
        
        search_service = SearchService(db)
        result = search_service.search_documents(search_request, db)
        
        return {
            "query": query,
            "total_results": result.total_count,
            "documents": [
                {
                    "id": doc.id,
                    "title": doc.title,
                    "filename": doc.filename,
                    "summary": doc.summary[:200] if doc.summary else None
                }
                for doc in result.documents
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Semantic search failed: {str(e)}")

@router.get("/test-fulltext")
def test_fulltext_search(
    query: str = Query(..., description="Test query for full-text search"),
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Test endpoint for full-text search functionality"""
    try:
        # Create a simple search request
        search_request = SearchRequest(
            query=query,
            limit=limit,
            use_semantic_search=False
        )
        
        search_service = SearchService(db)
        result = search_service.search_documents(search_request, db)
        
        return {
            "query": query,
            "total_results": result.total_count,
            "documents": [
                {
                    "id": doc.id,
                    "title": doc.title,
                    "filename": doc.filename,
                    "summary": doc.summary[:200] if doc.summary else None
                }
                for doc in result.documents
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Full-text search failed: {str(e)}")

@router.get("/vector-stats")
def get_vector_db_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Get statistics about the vector database"""
    try:
        from ..services.vector_db_service import VectorDBService
        vector_db = VectorDBService(db)
        return vector_db.get_collection_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get vector DB stats: {str(e)}")

@router.post("/rebuild-embeddings")
def rebuild_embeddings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update"))
):
    """Rebuild all document embeddings (admin function)"""
    try:
        from ..services.vector_db_service import VectorDBService
        from ..models import Document, ProcessingLog

        vector_db = VectorDBService(db)

        # Reset collection
        vector_db.reset_collection()
        
        # Log the start of reembedding process
        start_log = ProcessingLog(
            document_id=None,
            operation="reembedding_start",
            status="info",
            message="Started reembedding process for all documents"
        )
        db.add(start_log)
        db.commit()
        
        # Rebuild embeddings for all documents
        documents = db.query(Document).filter(Document.full_text.isnot(None)).all()
        
        processed = 0
        errors = 0
        
        # Import document processor once
        from ..services.document_processor import DocumentProcessor
        processor = DocumentProcessor(db)

        for doc in documents:
            try:
                # Use document processor's embedding generation for consistency
                processor._store_embeddings(doc, db)
                
                # Log successful reembedding for this document
                success_log = ProcessingLog(
                    document_id=doc.id,
                    operation="reembedding",
                    status="success",
                    message=f"Successfully reembedded document: {doc.title or doc.filename}"
                )
                db.add(success_log)
                
                processed += 1
                
            except Exception as e:
                # Log error for this document
                error_log = ProcessingLog(
                    document_id=doc.id,
                    operation="reembedding",
                    status="error",
                    message=f"Failed to reembed document: {str(e)}"
                )
                db.add(error_log)
                errors += 1
                continue
        
        # Log the completion of reembedding process
        completion_log = ProcessingLog(
            document_id=None,
            operation="reembedding_complete",
            status="success",
            message=f"Completed reembedding process: {processed} processed, {errors} errors"
        )
        db.add(completion_log)
        db.commit()
        
        return {
            "message": "Embeddings rebuilt successfully",
            "processed": processed,
            "errors": errors,
            "total_documents": len(documents)
        }
        
    except Exception as e:
        # Log general failure
        failure_log = ProcessingLog(
            document_id=None,
            operation="reembedding_complete",
            status="error",
            message=f"Reembedding process failed: {str(e)}"
        )
        db.add(failure_log)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to rebuild embeddings: {str(e)}")
