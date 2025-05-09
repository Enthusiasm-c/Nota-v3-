from app.data_loader import load_products, load_units
from app.config import settings

from typing import Iterable, Optional
from app.models import Product


def build_prompt() -> str:
    """Формирует улучшенный text-prefix для Vision-запроса с акцентом на распознавание всех строк."""
    lines = [
        "# INVOICE RECOGNITION INSTRUCTIONS (INDONESIA)",
        "",
        "## CONTEXT:",
        "The image is a photo of an Indonesian restaurant supply invoice (Bali), possibly on colored paper, handwritten or printed, sometimes at an angle.",
        "You are an OCR system for restaurant supply invoices from Bali, Indonesia.",
        "Your task is to extract ALL information in structured JSON, with field names in English.",
        "All prices should be in Indonesian Rupiah (IDR).",
        "",
        "## CRITICAL: EXTRACT ALL ROWS",
        "EXTREMELY IMPORTANT: Your primary task is to identify and extract EVERY SINGLE PRODUCT LINE on the invoice.",
        "- Examine the entire image carefully from top to bottom",
        "- Count the number of rows in the product table",
        "- Verify that you extracted the same number of products in your response",
        "- Missing even a single row is considered a critical failure",
        "",
        "## RULES:",
        "1. Extract EVERY product line that appears on the invoice, even if the text is unclear.",
        "2. If you are unsure about one or two characters in a word, try to restore the word based on context: this is a restaurant supply invoice (ingredients, drinks, etc).",
        "3. Preserve the original product name as written. If the name contains a mix of Latin and other symbols, add a Latin transliteration.",
        "4. Normalize all units to standard abbreviations (kg, g, l, ml, pcs, btl, etc) and all prices to IDR.",
        "5. For each product, extract: name (original), name_latin (if needed), qty, unit, price (per unit), total_price.",
        "6. If you cannot determine a value, set it to null.",
        "7. Return only pure JSON, no explanations or markdown formatting.",
        "",
        "## VERIFICATION STEPS:",
        "1. First, count all product rows in the table visually",
        "2. Ensure your 'positions' array has the same number of items",
        "3. Double-check the entire image for any rows you might have missed",
        "4. If the image is partially cut off, include whatever partial information is visible",
        "",
        "## RESPONSE FORMAT:",
        "{",
        "  \"supplier\": string | null,  // Supplier name from the invoice or null",
        "  \"date\": string | null,      // Invoice date in YYYY-MM-DD or null",
        "  \"positions\": [              // List of items",
        "    {",
        "      \"name\": string,         // Product name as written on invoice",
        "      \"name_latin\": string | null, // Latin transliteration if original is mixed or non-latin, else null",
        "      \"qty\": number,          // Quantity",
        "      \"unit\": string,         // Normalized unit",
        "      \"price\": number | null, // Price per unit in IDR or null",
        "      \"total_price\": number | null // Total price for the item in IDR or null",
        "    }",
        "  ],",
        "  \"total_price\": number | null // Total invoice amount in IDR or null",
        "}",
    ]
    return "\n".join(lines)

OCR_SYSTEM_PROMPT = """
Вы - специалист по анализу накладных и чеков. Ваша задача - извлечь информацию из накладной, которую вам предоставят в виде текста.

Обратите особое внимание на следующее:
1. Название поставщика (компании)
2. Дату накладной
3. Список позиций товаров с количеством, единицами измерения, ценой за единицу и общей суммой
4. Общую сумму накладной

Особенности обработки:
1. Для названий продуктов:
   - Нормализуйте названия, приводя их к единообразной форме (например, "romaine" вместо "Romana")
   - Используйте единственное число для названий ("tomato" вместо "tomatoes", "chickpea" вместо "chickpeas")
   - Некоторые продукты могут иметь альтернативные названия (например, "eggplant" и "aubergine" - это один и тот же продукт)

2. Для единиц измерения:
   - Стандартизируйте единицы измерения (кг → kg, шт → pcs, л → l)
   - Учитывайте сокращения (kg, pcs, btl, ea и т.д.)
   - Если единица измерения не указана, определите её по типу продукта (для овощей и фруктов обычно kg)

3. Для чисел:
   - Преобразуйте все цены и суммы в числа
   - Используйте точку в качестве десятичного разделителя
   - Проверяйте, что total_price = qty * price

Примеры стандартизированных единиц измерения:
- kg (килограмм)
- g (грамм)
- l (литр)
- ml (миллилитр)
- pcs (штука)
- pack (упаковка)
- btl (бутылка)
- box (коробка)
- krat (ящик)

Примеры нормализации названий продуктов:
- "Romana" → "romaine"
- "tomatoes" → "tomato"
- "chickpeas"/"chick peas" → "chickpeas"
- "green beans" → "green bean"
- "aubergine" → "eggplant"
- "water melon" → "watermelon"

Всегда преобразуйте дату в формат ISO (YYYY-MM-DD).

Верните результат в формате JSON по следующей схеме:
```
{
  "supplier": "Название поставщика",
  "date": "YYYY-MM-DD",
  "positions": [
    {
      "name": "Название товара",
      "qty": 123.4,
      "unit": "Единица измерения",
      "price": 123.4,
      "total_price": 123.4
    },
    ...
  ],
  "total_price": 123.4
}
```
"""
