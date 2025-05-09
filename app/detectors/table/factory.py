from app.detectors.table.interface import TableDetector
from app.detectors.table.paddle_detector import PaddleTableDetector
import logging

def get_detector(method="paddle") -> TableDetector:
    """
    Фабрика для создания детектора таблиц.
    
    Args:
        method: Метод детекции таблиц ('paddle' или будущие реализации)
        
    Returns:
        TableDetector: Экземпляр детектора таблиц
    """
    if method == "paddle":
        return PaddleTableDetector()
    else:
        logging.warning(f"Неизвестный метод детекции таблиц: {method}. Используется PaddleTableDetector.")
        return PaddleTableDetector()