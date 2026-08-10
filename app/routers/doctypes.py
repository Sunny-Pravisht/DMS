from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List

from ..database import get_db
from ..models import DocType, Document, User
from ..schemas import DocType as DocTypeSchema, DocTypeCreate, DocTypeUpdate, DocTypeWithCount
from ..services.auth_service import require_permission_flexible

router = APIRouter()

@router.get("/", response_model=List[DocTypeWithCount])
def get_doctypes(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("doctypes.read"))
):
    """Get all document types with document counts, sorted alphabetically"""
    results = (
        db.query(
            DocType,
            func.count(Document.id).label('document_count')
        )
        .outerjoin(Document, Document.doctype_id == DocType.id)
        .group_by(DocType.id)
        .order_by(DocType.name.asc())  # Sort alphabetically
        .offset(skip)
        .limit(limit)
        .all()
    )
    
    doctypes_with_count = []
    for doctype, count in results:
        doctype_dict = doctype.__dict__.copy()
        doctype_dict['document_count'] = count
        doctypes_with_count.append(doctype_dict)
    
    return doctypes_with_count

@router.get("/{doctype_id}", response_model=DocTypeSchema)
def get_doctype(
    doctype_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("doctypes.read"))
):
    """Get a specific document type by ID"""
    doctype = db.query(DocType).filter(DocType.id == doctype_id).first()
    if not doctype:
        raise HTTPException(status_code=404, detail="Document type not found")
    return doctype

@router.post("/", response_model=DocTypeSchema)
def create_doctype(
    doctype: DocTypeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("doctypes.create"))
):
    """Create a new document type"""
    # Check if doctype with same name already exists
    existing = db.query(DocType).filter(DocType.name == doctype.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Document type with this name already exists")
    
    db_doctype = DocType(**doctype.dict())
    db.add(db_doctype)
    db.commit()
    db.refresh(db_doctype)
    return db_doctype

@router.put("/{doctype_id}", response_model=DocTypeSchema)
def update_doctype(
    doctype_id: str,
    doctype_update: DocTypeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("doctypes.update"))
):
    """Update a document type"""
    doctype = db.query(DocType).filter(DocType.id == doctype_id).first()
    if not doctype:
        raise HTTPException(status_code=404, detail="Document type not found")
    
    # Check if new name conflicts with existing doctype
    if doctype_update.name and doctype_update.name != doctype.name:
        existing = db.query(DocType).filter(DocType.name == doctype_update.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Document type with this name already exists")
    
    # Update fields
    update_data = doctype_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(doctype, field, value)
    
    db.commit()
    db.refresh(doctype)
    return doctype

@router.delete("/{doctype_id}")
def delete_doctype(
    doctype_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("doctypes.delete"))
):
    """Delete a document type"""
    doctype = db.query(DocType).filter(DocType.id == doctype_id).first()
    if not doctype:
        raise HTTPException(status_code=404, detail="Document type not found")
    
    # Check if doctype is referenced by any documents
    from ..models import Document
    doc_count = db.query(Document).filter(Document.doctype_id == doctype_id).count()
    if doc_count > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot delete document type. {doc_count} documents are associated with this type."
        )
    
    db.delete(doctype)
    db.commit()
    return {"message": "Document type deleted successfully"}

@router.get("/{doctype_id}/documents")
def get_doctype_documents(
    doctype_id: str,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("doctypes.read"))
):
    """Get all documents for a specific document type"""
    doctype = db.query(DocType).filter(DocType.id == doctype_id).first()
    if not doctype:
        raise HTTPException(status_code=404, detail="Document type not found")
    
    from ..models import Document
    documents = (db.query(Document)
                .filter(Document.doctype_id == doctype_id)
                .offset(skip)
                .limit(limit)
                .all())
    
    return {
        "doctype": doctype,
        "documents": documents,
        "total_documents": db.query(Document).filter(Document.doctype_id == doctype_id).count()
    }
