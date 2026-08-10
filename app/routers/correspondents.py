from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List

from ..database import get_db
from ..models import Correspondent, Document, User
from ..schemas import Correspondent as CorrespondentSchema, CorrespondentWithCount
from ..schemas_validated import ValidatedCorrespondentCreate as CorrespondentCreate, ValidatedCorrespondentUpdate as CorrespondentUpdate
from ..services.auth_service import require_permission_flexible
from ..utils.validators import validate_pagination, ValidationError

router = APIRouter()

@router.get("/", response_model=List[CorrespondentWithCount])
def get_correspondents(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("correspondents.read"))
):
    """Get all correspondents with document counts, sorted alphabetically"""
    # Validate pagination parameters
    try:
        skip, limit = validate_pagination(skip, limit, max_limit=100)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    results = (
        db.query(
            Correspondent,
            func.count(Document.id).label('document_count')
        )
        .outerjoin(Document, Document.correspondent_id == Correspondent.id)
        .group_by(Correspondent.id)
        .order_by(Correspondent.name.asc())  # Sort alphabetically
        .offset(skip)
        .limit(limit)
        .all()
    )
    
    correspondents_with_count = []
    for correspondent, count in results:
        correspondent_dict = correspondent.__dict__.copy()
        correspondent_dict['document_count'] = count
        correspondents_with_count.append(correspondent_dict)
    
    return correspondents_with_count

@router.get("/{correspondent_id}", response_model=CorrespondentSchema)
def get_correspondent(
    correspondent_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("correspondents.read"))
):
    """Get a specific correspondent by ID"""
    correspondent = db.query(Correspondent).filter(Correspondent.id == correspondent_id).first()
    if not correspondent:
        raise HTTPException(status_code=404, detail="Correspondent not found")
    return correspondent

@router.post("/", response_model=CorrespondentSchema)
def create_correspondent(
    correspondent: CorrespondentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("correspondents.create"))
):
    """Create a new correspondent"""
    # Check if correspondent with same name already exists
    existing = db.query(Correspondent).filter(Correspondent.name == correspondent.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Correspondent with this name already exists")
    
    db_correspondent = Correspondent(**correspondent.dict())
    db.add(db_correspondent)
    db.commit()
    db.refresh(db_correspondent)
    return db_correspondent

@router.put("/{correspondent_id}", response_model=CorrespondentSchema)
def update_correspondent(
    correspondent_id: str,
    correspondent_update: CorrespondentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("correspondents.update"))
):
    """Update a correspondent"""
    correspondent = db.query(Correspondent).filter(Correspondent.id == correspondent_id).first()
    if not correspondent:
        raise HTTPException(status_code=404, detail="Correspondent not found")
    
    # Check if new name conflicts with existing correspondent
    if correspondent_update.name and correspondent_update.name != correspondent.name:
        existing = db.query(Correspondent).filter(Correspondent.name == correspondent_update.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Correspondent with this name already exists")
    
    # Update fields
    update_data = correspondent_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(correspondent, field, value)
    
    db.commit()
    db.refresh(correspondent)
    return correspondent

@router.delete("/{correspondent_id}")
def delete_correspondent(
    correspondent_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("correspondents.delete"))
):
    """Delete a correspondent"""
    correspondent = db.query(Correspondent).filter(Correspondent.id == correspondent_id).first()
    if not correspondent:
        raise HTTPException(status_code=404, detail="Correspondent not found")
    
    # Check if correspondent is referenced by any documents
    from ..models import Document
    doc_count = db.query(Document).filter(Document.correspondent_id == correspondent_id).count()
    if doc_count > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot delete correspondent. {doc_count} documents are associated with this correspondent."
        )
    
    db.delete(correspondent)
    db.commit()
    return {"message": "Correspondent deleted successfully"}

@router.get("/{correspondent_id}/documents")
def get_correspondent_documents(
    correspondent_id: str,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("correspondents.read"))
):
    """Get all documents for a specific correspondent"""
    correspondent = db.query(Correspondent).filter(Correspondent.id == correspondent_id).first()
    if not correspondent:
        raise HTTPException(status_code=404, detail="Correspondent not found")
    
    from ..models import Document
    documents = (db.query(Document)
                .filter(Document.correspondent_id == correspondent_id)
                .offset(skip)
                .limit(limit)
                .all())
    
    return {
        "correspondent": correspondent,
        "documents": documents,
        "total_documents": db.query(Document).filter(Document.correspondent_id == correspondent_id).count()
    }
