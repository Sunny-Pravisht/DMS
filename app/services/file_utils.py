import hashlib
from pathlib import Path
from loguru import logger

def calculate_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """Calculate hash of a file"""
    hash_obj = hashlib.new(algorithm)
    
    try:
        with open(file_path, "rb") as f:
            # Read file in chunks to handle large files
            for chunk in iter(lambda: f.read(4096), b""):
                hash_obj.update(chunk)
        
        file_hash = hash_obj.hexdigest()
        logger.debug(f"Calculated {algorithm} hash for {file_path.name}: {file_hash}")
        return file_hash
        
    except Exception as e:
        logger.error(f"Failed to calculate hash for {file_path}: {e}")
        raise

def calculate_content_hash(content: bytes, algorithm: str = "sha256") -> str:
    """Calculate hash of content bytes"""
    hash_obj = hashlib.new(algorithm)
    hash_obj.update(content)
    return hash_obj.hexdigest()

def verify_file_integrity(file_path: Path, expected_hash: str, algorithm: str = "sha256") -> bool:
    """Verify file integrity against expected hash"""
    try:
        actual_hash = calculate_file_hash(file_path, algorithm)
        is_valid = actual_hash == expected_hash
        
        if not is_valid:
            logger.warning(f"File integrity check failed for {file_path.name}. "
                         f"Expected: {expected_hash}, Got: {actual_hash}")
        
        return is_valid
        
    except Exception as e:
        logger.error(f"Failed to verify file integrity for {file_path}: {e}")
        return False

def get_file_info(file_path: Path) -> dict:
    """Get comprehensive file information"""
    try:
        stat = file_path.stat()
        
        return {
            "name": file_path.name,
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "created": stat.st_ctime,
            "extension": file_path.suffix.lower(),
            "hash": calculate_file_hash(file_path)
        }
    except Exception as e:
        logger.error(f"Failed to get file info for {file_path}: {e}")
        raise
