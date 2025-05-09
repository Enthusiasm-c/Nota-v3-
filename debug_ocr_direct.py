#!/usr/bin/env python
"""
Скрипт для прямого тестирования OCR без использования Telegram бота.
Напрямую вызывает OCR и сравнивает результат с эталонным JSON.
"""

import asyncio
import json
import os
import time
import sys
import datetime
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

# Добавляем текущую директорию в путь для импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импортируем модули OCR
import app.ocr as ocr
from app.utils.processing_pipeline import process_invoice_pipeline

# Сериализатор JSON для поддержки даты
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        return super(DateTimeEncoder, self).default(obj)

async def test_ocr(image_path, reference_path=None):
    """
    Тестирует OCR для указанного изображения и сравнивает с эталоном.
    
    Args:
        image_path: Путь к тестовому изображению
        reference_path: Путь к эталонному JSON (опционально)
    """
    print(f"[*] Начинаю тестирование OCR для {image_path}")
    
    # Загружаем изображение
    with open(image_path, "rb") as f:
        img_bytes = f.read()
    
    # Временный путь для сохранения изображения
    tmp_path = f"/tmp/test_ocr_{int(time.time())}.jpg"
    
    # Генерируем идентификатор запроса
    req_id = f"test_{int(time.time())}"
    
    try:
        start_time = time.time()
        print(f"[*] Вызываю метод process_invoice_pipeline")
        
        # Вызываем pipeline обработки
        processed_bytes, ocr_result = await process_invoice_pipeline(
            img_bytes, tmp_path, req_id
        )
        
        elapsed = time.time() - start_time
        print(f"[+] OCR обработка завершена за {elapsed:.2f} сек")
        
        # Выводим общую информацию о результате
        if ocr_result and hasattr(ocr_result, 'positions'):
            positions_count = len(ocr_result.positions)
            print(f"[+] Найдено {positions_count} позиций")
            print(f"[+] Поставщик: {getattr(ocr_result, 'supplier', 'Не найден')}")
            print(f"[+] Дата: {getattr(ocr_result, 'date', 'Не найдена')}")
            
            # Сохраняем результат в JSON
            result_file = f"tmp/ocr_result_{int(time.time())}.json"
            try:
                # Преобразуем Pydantic модель в словарь, затем в JSON с поддержкой даты
                result_dict = ocr_result.model_dump() if hasattr(ocr_result, 'model_dump') else ocr_result.dict()
                with open(result_file, "w") as f:
                    json.dump(result_dict, f, indent=2, cls=DateTimeEncoder)
                print(f"[+] Результат сохранен в {result_file}")
            except Exception as json_err:
                print(f"[-] Ошибка при сохранении результата в JSON: {json_err}")
                import traceback
                traceback.print_exc()
            
            # Сравниваем с эталоном, если указан
            if reference_path:
                compare_with_reference(ocr_result, reference_path)
        else:
            print(f"[-] OCR не вернул структурированные данные: {ocr_result}")
        
    except Exception as e:
        print(f"[-] Ошибка при обработке: {e}")
        import traceback
        traceback.print_exc()

def compare_with_reference(ocr_result, reference_path):
    """
    Сравнивает результат OCR с эталонным JSON
    """
    print(f"\n[*] Сравниваю результат с эталоном {reference_path}")
    try:
        with open(reference_path, "r") as f:
            reference = json.load(f)
        
        # Преобразуем результат OCR в словарь
        result_dict = ocr_result.model_dump() if hasattr(ocr_result, 'model_dump') else ocr_result.dict()
        
        # Для строкового сравнения даты
        if isinstance(result_dict.get("date"), (datetime.datetime, datetime.date)):
            result_dict["date"] = result_dict["date"].isoformat()
        
        # Базовое сравнение
        if reference.get("supplier") == result_dict.get("supplier"):
            print(f"[+] Поставщик: {reference.get('supplier')} ✓")
        else:
            print(f"[-] Поставщик: {reference.get('supplier')} ≠ {result_dict.get('supplier')} ✗")
        
        if reference.get("date") == result_dict.get("date"):
            print(f"[+] Дата: {reference.get('date')} ✓")
        else:
            print(f"[-] Дата: {reference.get('date')} ≠ {result_dict.get('date')} ✗")
        
        # Сравнение позиций
        ref_positions = reference.get("positions", [])
        result_positions = result_dict.get("positions", [])
        
        print(f"[*] Сравнение позиций: эталон {len(ref_positions)}, результат {len(result_positions)}")
        
        # Создаем словарь позиций для быстрого сравнения
        ref_pos_dict = {p["name"]: p for p in ref_positions}
        result_pos_dict = {p["name"]: p for p in result_positions}
        
        # Проверяем наличие позиций
        found_exact = 0
        found_similar = 0
        missing = 0
        extra = 0
        
        for name, ref_pos in ref_pos_dict.items():
            if name in result_pos_dict:
                # Точное совпадение имени
                result_pos = result_pos_dict[name]
                if (ref_pos["qty"] == result_pos["qty"] and 
                    ref_pos["price"] == result_pos["price"] and 
                    ref_pos["total_price"] == result_pos["total_price"]):
                    found_exact += 1
                else:
                    found_similar += 1
                    print(f"[~] Позиция '{name}': частичное совпадение")
                    print(f"    Эталон:   кол-во: {ref_pos['qty']}, цена: {ref_pos['price']}, сумма: {ref_pos['total_price']}")
                    print(f"    Результат: кол-во: {result_pos['qty']}, цена: {result_pos['price']}, сумма: {result_pos['total_price']}")
            else:
                missing += 1
                print(f"[-] Позиция отсутствует: '{name}'")
        
        # Проверяем лишние позиции
        for name in result_pos_dict:
            if name not in ref_pos_dict:
                extra += 1
                print(f"[!] Лишняя позиция: '{name}'")
        
        print(f"\n[*] Итоги сравнения:")
        print(f"    Всего позиций в эталоне: {len(ref_positions)}")
        print(f"    Точные совпадения: {found_exact}")
        print(f"    Частичные совпадения: {found_similar}")
        print(f"    Отсутствующие позиции: {missing}")
        print(f"    Лишние позиции: {extra}")
        
        # Подсчитываем общий коэффициент качества
        if len(ref_positions) > 0:
            quality = (found_exact + found_similar * 0.5) / len(ref_positions) * 100
            print(f"[*] Общая оценка качества OCR: {quality:.1f}%")
    except Exception as e:
        print(f"[-] Ошибка при сравнении с эталоном: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """
    Основная функция скрипта
    """
    # Создаем директорию tmp, если не существует
    os.makedirs("tmp", exist_ok=True)
    
    # Проверяем аргументы
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        image_path = "data/sample/invoice_test.jpg"
    
    reference_path = "data/sample/invoice_reference.json"
    
    # Проверяем наличие файлов
    if not os.path.exists(image_path):
        print(f"[-] Изображение не найдено: {image_path}")
        return
    
    if not os.path.exists(reference_path):
        print(f"[!] Эталонный JSON не найден: {reference_path}")
        reference_path = None
    
    # Запускаем тестирование
    await test_ocr(image_path, reference_path)

if __name__ == "__main__":
    asyncio.run(main()) 