from sqlalchemy.orm import Session
from ..models import DocType, Document
from loguru import logger

# The application is English-only. Type names are single lowercase words because
# they become one underscore-separated segment of a document title.
DEFAULT_DOCUMENT_TYPES = [
    "invoice",
    "letter",
    "quote",
    "registration",
    "certificate",
    "payslip",
    "termination",
    "contract",
    "report",
    "receipt",
    "reminder",
    "credit",
    "order",
    "delivery",
    "minutes",
    "other",
]

# Used whenever the AI cannot classify a document.
FALLBACK_DOCUMENT_TYPE = "other"

# Installations seeded before the English-only switch carry the old German type
# names. Renaming them in place keeps every document's doctype_id valid.
LEGACY_TYPE_TRANSLATIONS = {
    "rechnung": "invoice",
    "anschreiben": "letter",
    "angebot": "quote",
    "anmeldung": "registration",
    "bescheinigung": "certificate",
    "entgeltabrechnung": "payslip",
    "kündigung": "termination",
    "kuendigung": "termination",
    "vertrag": "contract",
    "bericht": "report",
    "quittung": "receipt",
    "mahnung": "reminder",
    "gutschrift": "credit",
    "bestellung": "order",
    "lieferschein": "delivery",
    "protokoll": "minutes",
    "sonstiges": "other",
}


def translate_legacy_document_types(db: Session) -> int:
    """Rename legacy German document types to their English equivalents.

    If both the old and the new name exist, the documents on the legacy row are
    repointed to the English row and the legacy row is dropped, so no document
    loses its type.
    """
    renamed = 0
    try:
        by_name = {}
        for doctype in db.query(DocType).all():
            by_name.setdefault(doctype.name.lower(), []).append(doctype)

        for legacy_name, english_name in LEGACY_TYPE_TRANSLATIONS.items():
            for legacy in by_name.get(legacy_name, []):
                target = next(iter(by_name.get(english_name, [])), None)

                if target is not None and target.id != legacy.id:
                    db.query(Document).filter(Document.doctype_id == legacy.id).update(
                        {Document.doctype_id: target.id}, synchronize_session=False
                    )
                    db.delete(legacy)
                    logger.info(
                        f"Merged legacy document type '{legacy.name}' into '{target.name}'"
                    )
                else:
                    legacy.name = english_name
                    legacy.description = f"Standard document type: {english_name}"
                    by_name.setdefault(english_name, []).append(legacy)
                    logger.info(
                        f"Renamed legacy document type '{legacy_name}' to '{english_name}'"
                    )
                renamed += 1

        if renamed:
            db.commit()
    except Exception as e:
        logger.error(f"Failed to translate legacy document types: {e}")
        db.rollback()
        raise

    return renamed


def ensure_default_document_types(db: Session):
    """Ensure default document types exist in database"""

    default_types = DEFAULT_DOCUMENT_TYPES

    try:
        # Bring any pre-existing German type names over to English first, so the
        # English defaults below don't get added a second time alongside them.
        translate_legacy_document_types(db)

        # Check which types already exist
        existing_types = db.query(DocType).all()
        existing_names = {dt.name.lower() for dt in existing_types}

        # Add missing default types
        for doc_type in default_types:
            if doc_type.lower() not in existing_names:
                new_type = DocType(
                    name=doc_type,
                    description=f"Standard document type: {doc_type}"
                )
                db.add(new_type)
                logger.info(f"Added default document type: {doc_type}")
        
        db.commit()
        logger.info("Default document types ensured in database")
        
    except Exception as e:
        logger.error(f"Failed to ensure default document types: {e}")
        db.rollback()
        raise

def add_document_type_if_not_exists(db: Session, type_name: str, description: str = None) -> DocType:
    """Add a new document type if it doesn't exist"""
    
    try:
        # Check if type already exists (case insensitive)
        existing_type = db.query(DocType).filter(
            DocType.name.ilike(type_name)
        ).first()
        
        if existing_type:
            return existing_type
        
        # Create new type
        new_type = DocType(
            name=type_name.lower(),
            description=description or f"Document type: {type_name}"
        )
        db.add(new_type)
        db.commit()
        
        logger.info(f"Added new document type: {type_name}")
        return new_type
        
    except Exception as e:
        logger.error(f"Failed to add document type {type_name}: {e}")
        db.rollback()
        raise