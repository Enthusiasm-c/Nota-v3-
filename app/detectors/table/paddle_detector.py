from typing import List, Dict, Any
from app.detectors.table.interface import TableDetector
import logging
import tempfile
import numpy as np
from PIL import Image
import io

logger = logging.getLogger(__name__)

class PaddleTableDetector(TableDetector):
    def __init__(self):
        try:
            from paddleocr import PPStructure
            self.structure_engine = PPStructure(layout=True, show_log=False)
        except ImportError:
            self.structure_engine = None
            logger.error("PaddleOCR не установлен. Установите пакет paddleocr.")

    def detect(self, image_bytes: bytes) -> Dict[str, Any]:
        if not self.structure_engine:
            raise RuntimeError("PaddleOCR не инициализирован")
        # Конвертация bytes в изображение
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        np_img = np.array(image)
        # Вызов PPStructure
        logger.info("Запуск PPStructure для детекции таблицы...")
        result = self.structure_engine(np_img)
        # result — список структур по таблицам
        tables = []
        
        # Проверяем тип результата
        if not isinstance(result, list):
            logger.error(f"Некорректный формат результата PPStructure: {type(result)}, ожидался list. Результат: {result}")
            return {'tables': []}
            
        for item in result:
            if not isinstance(item, dict):
                logger.warning(f"Некорректный тип элемента в результате PPStructure: {type(item)}, ожидался dict. Элемент: {item}")
                continue
                
            if item.get('type') == 'table':
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
        
        # Проверяем тип результата
        if not isinstance(result, list):
            logger.error(f"Некорректный формат результата PPStructure: {type(result)}, ожидался list. Результат: {result}")
            return []
            
        # Вырезаем каждую ячейку
        for item in result:
            if not isinstance(item, dict):
                logger.warning(f"Некорректный тип элемента в результате PPStructure: {type(item)}, ожидался dict. Элемент: {item}")
                continue
                
            if item.get('type') == 'table':
                res = item.get('res', {})
                
                # Проверка на случай словаря с HTML-представлением таблицы
                if isinstance(res, dict) and 'cell_bbox' in res:
                    logger.info("Обнаружена таблица с HTML-представлением")
                    bboxes = res.get('cell_bbox', [])
                    
                    if not isinstance(bboxes, list):
                        logger.warning(f"Некорректный формат cell_bbox: {type(bboxes)}")
                        continue
                    
                    # Для каждой ячейки создаем отдельный элемент
                    for i, bbox in enumerate(bboxes):
                        if not isinstance(bbox, list) or len(bbox) != 8:
                            logger.warning(f"Некорректный формат bbox: {bbox}")
                            continue
                        
                        # Преобразуем 8-точечные координаты в стандартный bbox [x1, y1, x2, y2]
                        x_points = [bbox[0], bbox[2], bbox[4], bbox[6]]
                        y_points = [bbox[1], bbox[3], bbox[5], bbox[7]]
                        x1, y1 = min(x_points), min(y_points)
                        x2, y2 = max(x_points), max(y_points)
                        
                        # Корректируем координаты
                        x1 = max(0, int(x1))
                        y1 = max(0, int(y1))
                        x2 = min(image.width, int(x2))
                        y2 = min(image.height, int(y2))
                        
                        if x2 <= x1 or y2 <= y1:
                            logger.warning(f"Некорректные координаты ячейки: [{x1}, {y1}, {x2}, {y2}]")
                            continue
                        
                        # Вырезаем ячейку
                        cell_image = image.crop((x1, y1, x2, y2))
                        
                        # Преобразуем изображение ячейки в bytes
                        cell_bytes_io = io.BytesIO()
                        cell_image.save(cell_bytes_io, format='PNG')
                        cell_bytes = cell_bytes_io.getvalue()
                        
                        # Добавляем информацию о ячейке
                        cells.append({
                            'bbox': [x1, y1, x2, y2],
                            'image': cell_bytes,
                            'width': cell_image.width,
                            'height': cell_image.height,
                            'text': '',  # Текст будет заполнен после OCR
                            'structure': {}  # Структурная информация не используется
                        })
                elif isinstance(res, list):
                    # Оригинальная логика для списка ячеек
                    for cell in res:
                        if not isinstance(cell, dict):
                            logger.warning(f"Некорректный тип ячейки: {type(cell)}, ожидался dict. Содержимое: {cell}")
                            continue
                            
                        # Получаем координаты ячейки
                        bbox = cell.get('bbox')
                        if not bbox or not isinstance(bbox, list) or len(bbox) != 4:
                            logger.warning(f"Некорректные координаты ячейки: {bbox}")
                            continue
                        
                        # Корректируем координаты ячейки при необходимости
                        x1, y1, x2, y2 = bbox
                        x1 = max(0, x1)
                        y1 = max(0, y1)
                        x2 = min(image.width, x2)
                        y2 = min(image.height, y2)
                        
                        if x2 <= x1 or y2 <= y1:
                            logger.warning(f"Некорректные координаты ячейки: {bbox}")
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
                else:
                    logger.warning(f"Некорректный формат 'res' в таблице: {type(res)}. Содержимое: {res}")
        
        if not cells:
            logger.warning("Таблица не обнаружена или не содержит ячеек")
        else:
            logger.info(f"Извлечено {len(cells)} ячеек из таблицы")
            
        return cells 