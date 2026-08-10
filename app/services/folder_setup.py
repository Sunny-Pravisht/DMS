from pathlib import Path
from loguru import logger
from sqlalchemy.orm import Session
from ..config import get_settings

def setup_folders(db: Session = None):
    """Setup the required folder structure"""
    settings = get_settings(db)
    
    folders = [
        settings.staging_folder,
        settings.data_folder,
        settings.storage_folder,
        settings.logs_folder
    ]
    
    for folder in folders:
        folder_path = Path(folder)
        try:
            folder_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created/verified folder: {folder_path.absolute()}")
        except Exception as e:
            logger.error(f"Failed to create folder {folder_path}: {e}")
            raise

def select_root_folder():
    """Interactive folder selection (for CLI use)"""
    import tkinter as tk
    from tkinter import filedialog
    
    try:
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        
        folder_path = filedialog.askdirectory(
            title="Select Root Folder for Document Management System"
        )
        
        if folder_path:
            return Path(folder_path)
        else:
            return None
    except Exception as e:
        logger.error(f"Failed to open folder dialog: {e}")
        return None
    finally:
        try:
            root.destroy()
        except Exception:
            pass

def get_folder_info(db: Session = None):
    """Get information about the current folder structure"""
    settings = get_settings(db)
    
    info = {
        "staging": {
            "path": settings.staging_folder,
            "exists": Path(settings.staging_folder).exists(),
            "file_count": 0
        },
        "data": {
            "path": settings.data_folder,
            "exists": Path(settings.data_folder).exists(),
            "file_count": 0
        },
        "storage": {
            "path": settings.storage_folder,
            "exists": Path(settings.storage_folder).exists(),
            "file_count": 0
        }
    }
    
    # Count files in each folder
    for folder_name, folder_info in info.items():
        if folder_info["exists"]:
            try:
                folder_path = Path(folder_info["path"])
                folder_info["file_count"] = len([f for f in folder_path.iterdir() if f.is_file()])
            except Exception as e:
                logger.warning(f"Could not count files in {folder_path}: {e}")
    
    return info
