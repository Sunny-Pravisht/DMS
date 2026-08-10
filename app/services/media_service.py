"""
The image library behind the Studio's "Add images" panel.

Two sources feed it:

  * built-in marks shipped with the product (the brand logos and stamps), seeded
    once and then owned by the database like any other asset;
  * files a user browses to from their own machine.

Both end up as `MediaAsset` rows, so the Studio, the API and the PDF renderer
all address an image the same way - by id. No part of the system takes a file
path from the browser.
"""
from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from ..models import MediaAsset, User

BRAND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "ui" / "assets" / "brand"
UPLOAD_DIR = Path("data") / "assets" / "uploads"

ALLOWED_IMAGE_MIME = {
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp", "image/svg+xml",
}
ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
MAX_ASSET_BYTES = 8 * 1024 * 1024

# The five marks offered out of the box, plus the two seals. Order is the order
# they appear in the panel, so the company's own mark comes first.
BUILT_INS = [
    ("harman", "HARMAN logo", "logo", "harman.png"),
    ("maruti-suzuki", "Maruti Suzuki logo", "logo", "maruti-suzuki.png"),
    ("mahindra", "Mahindra logo", "logo", "mahindra.png"),
    ("tata", "Tata Motors logo", "logo", "tata.png"),
    ("stamp-approved", "Approved seal", "stamp", "stamp-approved.png"),
    ("stamp-confidential", "Confidential stamp", "stamp", "stamp-confidential.png"),
    ("harman-mark", "HARMAN mark", "logo", "harman-mark.png"),
]


class MediaError(ValueError):
    """The file offered is not something the library will store."""


def seed_builtins(db: Session) -> int:
    """Register the shipped marks. Idempotent; safe to call on every startup."""
    added = 0
    for key, name, kind, png in BUILT_INS:
        path = BRAND_DIR / png
        if not path.exists():
            logger.warning(f"Brand mark missing, not seeded: {path.name}. "
                           f"Run scripts/seed_brand_assets.py")
            continue

        asset = db.query(MediaAsset).filter(MediaAsset.key == key).first()
        if asset:
            # Keep the stored path honest if the project moved on disk.
            if asset.file_path != str(path):
                asset.file_path = str(path)
                db.commit()
            continue

        db.add(MediaAsset(
            key=key,
            name=name,
            kind=kind,
            file_path=str(path),
            mime_type="image/png",
            file_size=path.stat().st_size,
            is_builtin=True,
            is_shared=True,
        ))
        added += 1

    if added:
        db.commit()
        logger.info(f"Seeded {added} built-in image(s) into the library")
    return added


def list_assets(db: Session, user: Optional[User] = None, kind: Optional[str] = None):
    """Everything this user may place: the shared library plus their own uploads."""
    query = db.query(MediaAsset)
    if kind:
        query = query.filter(MediaAsset.kind == kind)
    if user is not None:
        query = query.filter(
            (MediaAsset.is_shared.is_(True)) | (MediaAsset.owner_id == user.id)
        )
    # Built-ins first, in seeding order, then the newest uploads.
    return query.order_by(MediaAsset.is_builtin.desc(), MediaAsset.created_at.desc()).all()


def get_asset(db: Session, asset_id: str, user: Optional[User] = None) -> Optional[MediaAsset]:
    asset = db.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
    if not asset:
        return None
    if user is not None and not asset.is_shared and asset.owner_id != user.id:
        return None
    return asset


def store_upload(db: Session, user: User, filename: str, content: bytes,
                 name: Optional[str] = None, kind: str = "image") -> MediaAsset:
    """Validate an uploaded image and add it to the library."""
    if not content:
        raise MediaError("That file is empty.")
    if len(content) > MAX_ASSET_BYTES:
        raise MediaError(f"Images must be under {MAX_ASSET_BYTES // (1024 * 1024)} MB.")

    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise MediaError(
            f"'{ext or filename}' is not an image. Use PNG, JPG, GIF, WEBP, BMP or SVG."
        )

    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    if mime not in ALLOWED_IMAGE_MIME:
        raise MediaError("That file does not look like an image.")

    # An SVG is a document, not a bitmap: it can carry script. Reject anything
    # with an executable payload rather than trying to clean it.
    if ext == ".svg":
        lowered = content[:8192].lower()
        if b"<script" in lowered or b"javascript:" in lowered or b"onload=" in lowered:
            raise MediaError("That SVG contains script and cannot be stored.")

    target_dir = UPLOAD_DIR / (user.id if user else "shared")
    target_dir.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256(content).hexdigest()[:16]
    safe_stem = "".join(c for c in Path(filename).stem if c.isalnum() or c in "-_")[:48] or "image"
    path = target_dir / f"{digest}_{safe_stem}{ext}"
    path.write_bytes(content)

    asset = MediaAsset(
        name=name or Path(filename).stem[:80] or "Uploaded image",
        kind=kind if kind in ("logo", "stamp", "signature", "image") else "image",
        file_path=str(path),
        mime_type=mime,
        file_size=len(content),
        is_builtin=False,
        is_shared=False,
        owner_id=user.id if user else None,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def delete_asset(db: Session, asset: MediaAsset) -> None:
    """Remove an uploaded asset. Built-ins are part of the product and stay."""
    if asset.is_builtin:
        raise MediaError("Built-in marks cannot be deleted.")
    try:
        Path(asset.file_path).unlink(missing_ok=True)
    except OSError as exc:
        logger.warning(f"Could not remove asset file {asset.file_path}: {exc}")
    db.delete(asset)
    db.commit()


def resolver(db: Session, user: Optional[User] = None):
    """
    Map an `<img src>` back to a file on disk, for the PDF renderer.

    Only two shapes resolve: an asset URL this API issued, and a static brand
    path. Everything else - notably any absolute URL - returns None and the
    image is simply left out of the PDF.
    """
    cache: dict[str, Optional[str]] = {}

    def resolve(src: str) -> Optional[str]:
        if not src or src in cache:
            return cache.get(src)

        path: Optional[str] = None

        if "/api/studio/assets/" in src:
            asset_id = src.split("/api/studio/assets/", 1)[1].split("/", 1)[0].split("?")[0]
            asset = get_asset(db, asset_id, user)
            if asset and Path(asset.file_path).exists():
                path = asset.file_path

        elif "/static/ui/assets/brand/" in src:
            name = Path(src.split("/static/ui/assets/brand/", 1)[1].split("?")[0]).name
            # SVG has no ReportLab reader; use the PNG rendered alongside it.
            candidate = BRAND_DIR / (Path(name).stem + ".png")
            if candidate.exists():
                path = str(candidate)

        cache[src] = path
        return path

    return resolve
