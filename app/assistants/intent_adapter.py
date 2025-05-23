"""
Адаптер для преобразования ответов от OpenAI Assistant API в валидный формат команд
для системы редактирования инвойсов.

Этот модуль служит промежуточным слоем между внешним API и внутренней системой,
обеспечивая совместимость форматов и устойчивость к ошибкам.
"""

import json
import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from app.utils.redis_cache import cache_get, cache_set

logger = logging.getLogger(__name__)

# Redis TTL для кешированных команд (12 часов)
INTENT_CACHE_TTL = 3600 * 12

# Ключ для самых распространенных паттернов команд
COMMON_PATTERNS_KEY = "intent:common_patterns"

class IntentAdapter:
    """
    Адаптер для преобразования ответов OpenAI в валидные команды.
    
    Основные функции:
    1. Нормализация форматов полей
    2. Проверка обязательных полей для каждого типа действия
    3. Преобразование индексов строк из 1-based в 0-based
    4. Приведение типов данных к ожидаемым форматам
    5. Извлечение JSON из текстовых ответов
    """
    
    # Определяем требуемые поля для каждого типа действия
    REQUIRED_FIELDS = {
        "set_date": ["value"],
        "set_price": ["line_index", "value"],
        "set_name": ["line_index", "value"],
        "set_quantity": ["line_index", "value"],
        "set_unit": ["line_index", "value"],
        "add_line": ["name", "qty", "unit", "price"],
    }
    
    # Месяцы для преобразования текстовых дат
    MONTHS = {
        "января": 1, "февраля": 2, "марта": 3, "апреля": 4, 
        "мая": 5, "июня": 6, "июля": 7, "августа": 8, 
        "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
        "январь": 1, "февраль": 2, "март": 3, "апрель": 4, 
        "май": 5, "июнь": 6, "июль": 7, "август": 8, 
        "сентябрь": 9, "октябрь": 10, "ноябрь": 11, "декабрь": 12,
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
    }
    
    # Паттерны регулярных выражений для быстрого распознавания команд
    FAST_PATTERNS = {
        # Цена: строка 1 цена 100
        r'(?:строк[аи]?|line|row)\s+(\d+).*?(?:цен[аыу]|price)\s+(\d+)': 
            lambda m: {"action": "set_price", "line_index": int(m.group(1))-1, "value": m.group(2)},
        
        # Количество: строка 2 количество 5
        r'(?:строк[аи]?|line|row)\s+(\d+).*?(?:кол-во|количество|qty|quantity)\s+(\d+)': 
            lambda m: {"action": "set_quantity", "line_index": int(m.group(1))-1, "value": m.group(2)},
        
        # Единица измерения: строка 3 ед изм кг
        r'(?:строк[аи]?|line|row)\s+(\d+).*?(?:ед\.?\s*изм\.?|unit)\s+(\w+)': 
            lambda m: {"action": "set_unit", "line_index": int(m.group(1))-1, "value": m.group(2)},
        
        # Название: строка 1 название Apple
        r'(?:строк[аи]?|line|row)\s+(\d+).*?(?:имя|название|name)\s+(.+?)(?:$|\s+(?:цен|кол|ед))': 
            lambda m: {"action": "set_name", "line_index": int(m.group(1))-1, "value": m.group(2).strip()},
        
        # Дата: дата 15 мая
        r'дат[аы]?\s+(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)':
            lambda m: {"action": "set_date", "value": f"{datetime.now().year}-{IntentAdapter.MONTHS.get(m.group(2), 1):02d}-{int(m.group(1)):02d}"},
        
        # Дата числовая: дата 15.05.2023
        r'дат[аы]?\s+(\d{1,2})[./](\d{1,2})(?:[./](\d{4}))?':
            lambda m: {"action": "set_date", "value": f"{m.group(3) or datetime.now().year}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"}
    }
    
    @classmethod
    def adapt(cls, response: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Основной метод адаптации ответа от OpenAI в валидный формат команд.
        
        Args:
            response: Ответ от OpenAI (строка или словарь)
            
        Returns:
            Dict: Нормализованная команда в формате {"action": "...", ...}
        """
        try:
            # ОПТИМИЗАЦИЯ: Быстрая обработка строковых команд через регулярные выражения
            if isinstance(response, str):
                fast_result = cls._fast_recognize(response)
                if fast_result:
                    logger.info(f"[IntentAdapter] Быстрое распознавание команды: {fast_result.get('action')}")
                    return fast_result
                
                # Попытка кешировать и получить из кеша
                cache_key = f"intent:normalized:{cls._normalize_for_cache(response)}"
                cached_intent = cache_get(cache_key)
                if cached_intent:
                    try:
                        intent = json.loads(cached_intent)
                        logger.info(f"[IntentAdapter] Использую кешированную команду: {intent.get('action')}")
                        return intent
                    except Exception as cache_err:
                        logger.warning(f"[IntentAdapter] Ошибка при разборе кешированной команды: {cache_err}")
            
            # Продолжаем с исходным алгоритмом
            # Если получили строку, пытаемся извлечь JSON
            if isinstance(response, str):
                intent = cls._extract_json(response)
            else:
                intent = response
                
            # Проверяем, есть ли поле action или actions
            if not isinstance(intent, dict):
                logger.error(f"Ответ не является словарем: {intent}")
                return {"action": "unknown", "error": "not_a_dict"}
                
            # Обработка массива actions
            if "actions" in intent and isinstance(intent["actions"], list) and len(intent["actions"]) > 0:
                logger.info(f"Найден массив actions, извлекаем первое действие: {intent['actions'][0]}")
                # Извлекаем первое действие из массива
                action_item = intent["actions"][0]
                if isinstance(action_item, dict) and "action" in action_item:
                    # Используем первое действие из массива
                    intent = action_item
                else:
                    logger.error(f"Элемент массива actions не содержит поле 'action': {action_item}")
                    return {"action": "unknown", "error": "invalid_action_in_array"}
            
            # Финальная проверка на наличие поля action
            if "action" not in intent:
                logger.error(f"Ответ не содержит поле 'action': {intent}")
                return {"action": "unknown", "error": "missing_action_field"}
                
            # Нормализуем команду в зависимости от типа действия
            action = intent.get("action")
            
            # Проверяем, поддерживается ли действие
            if action not in cls.REQUIRED_FIELDS:
                logger.warning(f"Неизвестное действие: {action}")
                return {"action": "unknown", "error": f"unsupported_action: {action}"}
                
            # Нормализуем поля в зависимости от типа действия
            normalized = cls._normalize_fields(intent)
            
            # Проверяем наличие обязательных полей
            missing_fields = cls._check_required_fields(normalized)
            if missing_fields:
                logger.error(f"Отсутствуют обязательные поля {missing_fields} для действия {action}")
                return {"action": "unknown", "error": f"missing_fields: {', '.join(missing_fields)}"}
                
            # ОПТИМИЗАЦИЯ: Кешируем результат для будущих похожих запросов
            if isinstance(response, str):
                cache_key = f"intent:normalized:{cls._normalize_for_cache(response)}"
                cache_set(cache_key, json.dumps(normalized), ex=INTENT_CACHE_TTL)
                logger.debug(f"Команда кеширована по ключу: {cache_key}")
                
            return normalized
            
        except Exception as e:
            logger.exception(f"Ошибка адаптации ответа: {e}")
            return {"action": "unknown", "error": str(e)}
    
    @classmethod
    def _fast_recognize(cls, text: str) -> Optional[Dict[str, Any]]:
        """
        Быстрое распознавание команд с использованием регулярных выражений
        
        Args:
            text: Текстовая команда
            
        Returns:
            Dict или None: Распознанная команда или None
        """
        normalized_text = text.lower().strip()
        
        for pattern, handler in cls.FAST_PATTERNS.items():
            match = re.search(pattern, normalized_text)
            if match:
                try:
                    result = handler(match)
                    logger.debug(f"Быстро распознана команда: {result}")
                    return result
                except Exception as e:
                    logger.warning(f"Ошибка при быстром распознавании команды: {e}")
        
        return None
    
    @classmethod
    def _normalize_for_cache(cls, text: str) -> str:
        """
        Нормализует текст для использования в качестве ключа кеша
        
        Args:
            text: Исходный текст
            
        Returns:
            str: Нормализованный ключ кеша
        """
        # Переводим в нижний регистр и удаляем лишние пробелы
        normalized = text.lower().strip()
        # Заменяем числа на плейсхолдеры
        normalized = re.sub(r'\d+', 'X', normalized)
        # Заменяем единицы измерения на плейсхолдеры
        units = ['кг', 'г', 'л', 'мл', 'шт', 'kg', 'g', 'l', 'ml', 'pcs']
        for unit in units:
            normalized = normalized.replace(unit, 'UNIT')
        # Удаляем лишние пробелы
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized
    
    @classmethod
    def _extract_json(cls, text: str) -> Dict[str, Any]:
        """
        Извлекает JSON из текстового ответа.
        
        Args:
            text: Текстовый ответ от API
            
        Returns:
            Dict: Извлеченный JSON или словарь с ошибкой
        """
        try:
            # Если весь текст - валидный JSON, используем его
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
                
            # Пытаемся найти JSON в тексте
            if "{" in text and "}" in text:
                # Ищем самый большой фрагмент, похожий на JSON
                start = text.find("{")
                end = text.rfind("}") + 1
                json_str = text[start:end]
                
                try:
                    parsed_json = json.loads(json_str)
                    
                    # Проверяем, содержит ли JSON поле actions или action
                    if isinstance(parsed_json, dict):
                        if "actions" in parsed_json or "action" in parsed_json:
                            # Уменьшаем логи в production - записываем только базовую информацию
                            logger.info("Успешно извлечен JSON с полем actions/action")
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(f"Содержимое JSON: {json_str[:100]}...")
                            return parsed_json
                        else:
                            # Записываем debug информацию только при включенном DEBUG уровне
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(f"Извлеченный JSON не содержит поля actions/action: {parsed_json}")
                    return parsed_json
                except json.JSONDecodeError:
                    logger.warning(f"Не удалось распарсить основной JSON фрагмент: {json_str[:100]}...")
                    # Если основной фрагмент не распарсился, попробуем найти другие JSON-фрагменты
                    all_start_indices = [i for i, char in enumerate(text) if char == "{"]
                    all_end_indices = [i + 1 for i, char in enumerate(text) if char == "}"]
                    
                    # Сортируем фрагменты по размеру (сначала проверяем большие фрагменты)
                    fragments = []
                    for s in all_start_indices:
                        for e in all_end_indices:
                            if s < e:
                                fragments.append((s, e, e - s))
                    
                    # Сортируем по размеру (от большего к меньшему)
                    fragments.sort(key=lambda x: x[2], reverse=True)
                    
                    for s, e, _ in fragments:
                        try:
                            json_candidate = text[s:e]
                            parsed_json = json.loads(json_candidate)
                            
                            # Проверяем, содержит ли JSON поле actions или action
                            if isinstance(parsed_json, dict):
                                if "actions" in parsed_json or "action" in parsed_json:
                                    logger.info("Successfully extracted alternative JSON with actions/action field")
                                    if logger.isEnabledFor(logging.DEBUG):
                                        logger.debug(f"JSON content: {json_candidate[:100]}...")
                                    return parsed_json
                            
                            # Если нашли любой валидный JSON, возвращаем его
                            logger.info("Successfully extracted alternative JSON")
                            return parsed_json
                        except json.JSONDecodeError:
                            continue
            
            # Если JSON не найден, пытаемся распознать команды в тексте
            return cls._parse_text_intent(text)
            
        except Exception as e:
            logger.exception(f"Ошибка извлечения JSON: {e}")
            return {"action": "unknown", "error": f"json_extraction_failed: {str(e)}"}
    
    @classmethod
    def _parse_text_intent(cls, text: str) -> Dict[str, Any]:
        """
        Пытается распознать команды из текстового ответа, если JSON не найден.
        
        Args:
            text: Текстовый ответ от API
            
        Returns:
            Dict: Распознанная команда или словарь с ошибкой
        """
        text_lower = text.lower()
        
        # Распознавание команды изменения даты
        if ("дат" in text_lower or "date" in text_lower):
            # Ищем числа (день) и месяцы в тексте
            day = None
            month = None
            year = datetime.now().year  # По умолчанию текущий год
            
            # Ищем день (число)
            day_match = re.search(r'(\d{1,2})(?:\s+|[-./])(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря|january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', text_lower)
            if day_match:
                day = int(day_match.group(1))
            
            # Ищем месяц (название)
            for month_name in cls.MONTHS:
                if month_name in text_lower:
                    month = cls.MONTHS[month_name]
                    break
            
            # Ищем год (4 цифры)
            year_match = re.search(r'\b(202\d)\b', text)
            if year_match:
                year = int(year_match.group(1))
            
            # Если нашли и день, и месяц
            if day and month:
                # Форматируем в стандартный формат YYYY-MM-DD
                return {"action": "set_date", "value": f"{year}-{month:02d}-{day:02d}"}
        
        # Распознавание команды изменения цены
        price_match = re.search(r'(строк[аи]?|line|row)\s+(\d+).*?(цен[аы]|price)\s+(\d+)', text_lower)
        if price_match:
            try:
                line = int(price_match.group(2))
                price = price_match.group(4)
                
                # Преобразуем в 0-based индекс
                line_index = line - 1
                
                return {"action": "set_price", "line_index": line_index, "value": price}
            except Exception:
                pass
        
        # Распознавание команды изменения наименования
        name_match = re.search(r'(строк[аи]?|line|row)\s+(\d+).*?(имя|название|name)\s+(.+?)(?:\s*$|\s+\w+\s+)', text_lower)
        if name_match:
            try:
                line = int(name_match.group(2))
                name = name_match.group(4).strip()
                
                # Преобразуем в 0-based индекс
                line_index = line - 1
                
                return {"action": "set_name", "line_index": line_index, "value": name}
            except Exception:
                pass
        
        # Не удалось распознать команду
        return {"action": "unknown", "error": "unparseable_text"}
    
    @classmethod
    def _normalize_fields(cls, intent: Dict[str, Any]) -> Dict[str, Any]:
        """
        Нормализует поля команды в зависимости от типа действия.
        
        Args:
            intent: Исходная команда
            
        Returns:
            Dict: Нормализованная команда
        """
        action = intent.get("action")
        normalized = {"action": action}
        
        try:
            # Обработка общих преобразований
            
            # 1. Преобразование line/row -> line_index (из 1-based в 0-based)
            if "line" in intent and "line_index" not in intent:
                try:
                    # Отнимаем 1, чтобы преобразовать из 1-based в 0-based
                    normalized["line_index"] = int(intent["line"]) - 1
                except (ValueError, TypeError):
                    normalized["line_index"] = 0  # Значение по умолчанию
            elif "row" in intent and "line_index" not in intent:
                try:
                    # Отнимаем 1, чтобы преобразовать из 1-based в 0-based
                    normalized["line_index"] = int(intent["row"]) - 1
                    logger.info(f"Преобразовано поле 'row' в 'line_index': {normalized['line_index']}")
                except (ValueError, TypeError):
                    normalized["line_index"] = 0  # Значение по умолчанию
            elif "line_index" in intent:
                normalized["line_index"] = intent["line_index"]
            
            # 2. Обработка действия set_date
            if action == "set_date":
                if "date" in intent and "value" not in intent:
                    normalized["value"] = cls._normalize_date(intent["date"])
                elif "value" in intent:
                    normalized["value"] = cls._normalize_date(intent["value"])
            
            # 3. Обработка действий с ценой и количеством
            elif action in ["set_price", "set_quantity"]:
                # Преобразование ключей qty -> value и price -> value
                if action == "set_price" and "price" in intent and "value" not in intent:
                    normalized["value"] = str(intent["price"])
                elif action == "set_quantity" and "qty" in intent and "value" not in intent:
                    normalized["value"] = str(intent["qty"])
                elif "value" in intent:
                    normalized["value"] = str(intent["value"])
            
            # 4. Обработка единиц измерения
            elif action == "set_unit":
                if "unit" in intent and "value" not in intent:
                    normalized["value"] = str(intent["unit"])
                elif "value" in intent:
                    normalized["value"] = str(intent["value"])
            
            # 5. Обработка наименования
            elif action == "set_name":
                if "name" in intent and "value" not in intent:
                    normalized["value"] = str(intent["name"])
                elif "value" in intent:
                    normalized["value"] = str(intent["value"])
            
            # 6. Обработка добавления строки
            elif action == "add_line":
                for field in ["name", "qty", "unit", "price"]:
                    if field in intent:
                        normalized[field] = str(intent[field])
            
            # Добавляем все остальные поля без изменений
            for key, value in intent.items():
                if key not in ["action", "line", "date"] and key not in normalized:
                    normalized[key] = value
            
            return normalized
            
        except Exception as e:
            logger.exception(f"Ошибка нормализации полей: {e}")
            return {"action": "unknown", "error": f"field_normalization_failed: {str(e)}"}
    
    @classmethod
    def _check_required_fields(cls, intent: Dict[str, Any]) -> List[str]:
        """
        Проверяет наличие всех требуемых полей для данного типа действия.
        
        Args:
            intent: Команда для проверки
            
        Returns:
            List[str]: Список отсутствующих полей (пустой, если все поля присутствуют)
        """
        action = intent.get("action")
        
        if action not in cls.REQUIRED_FIELDS:
            return []
            
        required = cls.REQUIRED_FIELDS[action]
        missing = [field for field in required if field not in intent]
        
        return missing
    
    @classmethod
    def _normalize_date(cls, date_value: str) -> str:
        """
        Преобразует различные форматы дат в стандартный формат YYYY-MM-DD.
        
        Args:
            date_value: Исходное значение даты
            
        Returns:
            str: Дата в формате YYYY-MM-DD
        """
        # Если уже в формате YYYY-MM-DD, возвращаем как есть
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_value):
            return date_value
            
        try:
            # Пробуем разные форматы дат
            
            # 1. Формат "DD MM YYYY" или "DD MM" (русские названия месяцев)
            words = date_value.lower().split()
            day = None
            month = None
            year = datetime.now().year  # По умолчанию текущий год
            
            if len(words) >= 2:
                # Первое слово может быть числом (день)
                if words[0].isdigit() and 1 <= int(words[0]) <= 31:
                    day = int(words[0])
                    
                    # Второе слово может быть названием месяца
                    if words[1].lower() in cls.MONTHS:
                        month = cls.MONTHS[words[1].lower()]
                        
                        # Если есть третье слово и оно - год
                        if len(words) >= 3 and words[2].isdigit() and int(words[2]) > 2000:
                            year = int(words[2])
                            
                        # Формируем дату
                        if day and month:
                            return f"{year}-{month:02d}-{day:02d}"
            
            # 2. Формат "DD.MM.YYYY" или "DD-MM-YYYY"
            date_match = re.match(r'(\d{1,2})[./\-](\d{1,2})(?:[./\-](\d{4}))?', date_value)
            if date_match:
                day = int(date_match.group(1))
                month = int(date_match.group(2))
                if date_match.group(3):
                    year = int(date_match.group(3))
                    
                # Проверяем корректность даты
                if 1 <= day <= 31 and 1 <= month <= 12:
                    return f"{year}-{month:02d}-{day:02d}"
            
            # 3. Если ничего не подошло, возвращаем как есть
            return date_value
            
        except Exception as e:
            logger.exception(f"Ошибка нормализации даты: {e}")
            return date_value


# Функция-обертка для удобного использования
def adapt_intent(response: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Адаптирует ответ от OpenAI Assistant API в валидный формат команд.
    
    Args:
        response: Ответ от OpenAI (строка или словарь)
        
    Returns:
        Dict: Нормализованная команда
    """
    return IntentAdapter.adapt(response)