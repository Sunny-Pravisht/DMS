from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List

from ..database import get_db
from ..models import Tag, Document, document_tags, User
from ..schemas import Tag as TagSchema, TagCreate, TagUpdate, TagWithCount
from ..services.auth_service import require_permission_flexible

router = APIRouter()

@router.get("/", response_model=List[TagWithCount])
def get_tags(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("tags.read"))
):
    """Get all tags with document counts, sorted alphabetically"""
    results = (
        db.query(
            Tag,
            func.count(document_tags.c.document_id).label('document_count')
        )
        .outerjoin(document_tags, document_tags.c.tag_id == Tag.id)
        .group_by(Tag.id)
        .order_by(Tag.name.asc())  # Sort alphabetically
        .offset(skip)
        .limit(limit)
        .all()
    )
    
    tags_with_count = []
    for tag, count in results:
        tag_dict = tag.__dict__.copy()
        tag_dict['document_count'] = count
        tags_with_count.append(tag_dict)
    
    return tags_with_count

@router.get("/{tag_id}", response_model=TagSchema)
def get_tag(
    tag_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("tags.read"))
):
    """Get a specific tag by ID"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag

@router.post("/", response_model=TagSchema)
def create_tag(
    tag: TagCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("tags.create"))
):
    """Create a new tag"""
    # Check if tag with same name already exists
    existing = db.query(Tag).filter(Tag.name == tag.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tag with this name already exists")
    
    db_tag = Tag(**tag.dict())
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag

@router.put("/{tag_id}", response_model=TagSchema)
def update_tag(
    tag_id: str,
    tag_update: TagUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("tags.update"))
):
    """Update a tag"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    # Check if new name conflicts with existing tag
    if tag_update.name and tag_update.name != tag.name:
        existing = db.query(Tag).filter(Tag.name == tag_update.name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Tag with this name already exists")
    
    # Update fields
    update_data = tag_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tag, field, value)
    
    db.commit()
    db.refresh(tag)
    return tag

@router.delete("/{tag_id}")
def delete_tag(
    tag_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("tags.delete"))
):
    """Delete a tag"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    # Check if tag is referenced by any documents
    doc_count = db.query(Document).join(Document.tags).filter(Tag.id == tag_id).count()
    if doc_count > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot delete tag. {doc_count} documents are associated with this tag."
        )
    
    db.delete(tag)
    db.commit()
    return {"message": "Tag deleted successfully"}

@router.get("/{tag_id}/documents")
def get_tag_documents(
    tag_id: str,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("tags.read"))
):
    """Get all documents for a specific tag"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    
    documents = (db.query(Document)
                .join(Document.tags)
                .filter(Tag.id == tag_id)
                .offset(skip)
                .limit(limit)
                .all())
    
    total_documents = db.query(Document).join(Document.tags).filter(Tag.id == tag_id).count()
    
    return {
        "tag": tag,
        "documents": documents,
        "total_documents": total_documents
    }

@router.get("/popular/")
def get_popular_tags(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("tags.read"))
):
    """Get most popular tags (by document count)"""
    from sqlalchemy import func
    from ..models import document_tags
    
    popular_tags = (
        db.query(Tag, func.count(document_tags.c.document_id).label('document_count'))
        .join(document_tags, Tag.id == document_tags.c.tag_id)
        .group_by(Tag.id)
        .order_by(func.count(document_tags.c.document_id).desc())
        .limit(limit)
        .all()
    )
    
    return [
        {
            "tag": tag,
            "document_count": count
        }
        for tag, count in popular_tags
    ]
