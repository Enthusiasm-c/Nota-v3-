from typing import List, Dict, Any
from abc import ABC, abstractmethod

class TableDetector(ABC):
    @abstractmethod
    def detect(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Детектирует таблицу и ячейки на изображении.
        Возвращает структуру с координатами ячеек и таблицы.
        """
        pass

    @abstractmethod
    def extract_cells(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Извлекает содержимое ячеек в виде отдельных изображений или ROI.
        Возвращает список словарей с координатами и байтами ячеек.
        """
        pass 