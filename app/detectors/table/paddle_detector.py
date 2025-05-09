from typing import List, Dict, Any
from app.detectors.table.interface import TableDetector
import logging
import tempfile
import numpy as np
from PIL import Image
import io

class PaddleTableDetector(TableDetector):
    def __init__(self):
        try:
            from paddleocr import PPStructure
            self.structure_engine = PPStructure(layout=True, show_log=False)
        except ImportError:
            self.structure_engine = None
            logging.error("PaddleOCR не установлен. Установите пакет paddleocr.")

    def detect(self, image_bytes: bytes) -> Dict[str, Any]:
        if not self.structure_engine:
            raise RuntimeError("PaddleOCR не инициализирован")
        # Конвертация bytes в изображение
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        np_img = np.array(image)
        # Вызов PPStructure
        logging.info("Запуск PPStructure для детекции таблицы...")
        result = self.structure_engine(np_img)
        # result — список структур по таблицам
        tables = []
        for item in result:
            if item['type'] == 'table':
                tables.append({
                    'bbox': item.get('bbox'),
                    'cells': item.get('res', [])
                })
        return {'tables': tables}

    def extract_cells(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        if not self.structure_engine:
            raise RuntimeError("PaddleOCR не инициализирован")
            
        # Открываем изображение
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        np_img = np.array(image)
        
        # Запускаем детекцию
        result = self.structure_engine(np_img)
        cells = []
        
        # Вырезаем каждую ячейку
        for item in result:
            if item['type'] == 'table':
                for cell in item.get('res', []):
                    # Получаем координаты ячейки
                    bbox = cell.get('bbox')
                    if not bbox or len(bbox) != 4:
                        continue
                    
                    # Корректируем координаты ячейки при необходимости
                    x1, y1, x2, y2 = bbox
                    x1 = max(0, x1)
                    y1 = max(0, y1)
                    x2 = min(image.width, x2)
                    y2 = min(image.height, y2)
                    
                    if x2 <= x1 or y2 <= y1:
                        logging.warning(f"Некорректные координаты ячейки: {bbox}")
                        continue
                    
                    # Вырезаем ячейку
                    cell_image = image.crop((x1, y1, x2, y2))
                    
                    # Преобразуем изображение ячейки в bytes
                    cell_bytes_io = io.BytesIO()
                    cell_image.save(cell_bytes_io, format='PNG')
                    cell_bytes = cell_bytes_io.getvalue()
                    
                    # Добавляем информацию о ячейке
                    cells.append({
                        'bbox': bbox,
                        'image': cell_bytes,
                        'width': cell_image.width,
                        'height': cell_image.height,
                        'text': cell.get('text', ''),  # Текст, если доступен
                        'structure': cell.get('structure', {})  # Структурная информация
                    })
        
        return cells 