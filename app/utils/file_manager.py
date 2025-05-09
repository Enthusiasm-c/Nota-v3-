import os
import tempfile
import logging
import time
from pathlib import Path
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger(__name__)

TMP_DIRS = {
    "ocr": Path(tempfile.gettempdir()) / "nota",
    "test": Path("tmp"),
}
MAX_FILE_AGE = {
    "ocr": 24,  # часы
    "test": 2,
}

def ensure_temp_dirs() -> None:
    for dir_path in TMP_DIRS.values():
        os.makedirs(dir_path, exist_ok=True)
        logger.debug(f"Temp directory ensured: {dir_path}")

@contextmanager
def temp_file(prefix: str, suffix: str, dir_type: str = "ocr") -> Path:
    ensure_temp_dirs()
    dir_path = TMP_DIRS.get(dir_type, TMP_DIRS["ocr"])
    file_path = dir_path / f"{prefix}_{int(time.time())}{suffix}"
    try:
        yield file_path
    finally:
        logger.debug(f"Temp file created: {file_path}")

def cleanup_temp_files(force: bool = False) -> int:
    now = time.time()
    deleted_count = 0
    for dir_type, dir_path in TMP_DIRS.items():
        if not dir_path.exists():
            continue
        max_age_hours = MAX_FILE_AGE.get(dir_type, 24)
        max_age_seconds = max_age_hours * 3600
        for file_path in dir_path.glob("*"):
            if not file_path.is_file():
                continue
            file_age = now - os.path.getmtime(file_path)
            if force or file_age > max_age_seconds:
                try:
                    os.remove(file_path)
                    deleted_count += 1
                    logger.debug(f"Deleted old temp file: {file_path} (age: {file_age/3600:.1f}h)")
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {file_path}: {e}")
    return deleted_count

def save_test_image(image_bytes: bytes, req_id: str) -> Optional[Path]:
    ensure_temp_dirs()
    test_dir = TMP_DIRS["test"]
    file_path = test_dir / f"ocr_test_{req_id}.png"
    try:
        with open(file_path, "wb") as f:
            f.write(image_bytes)
        logger.info(f"Saved test image to {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Failed to save test image: {e}")
        return None 