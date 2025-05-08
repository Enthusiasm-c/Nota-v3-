from app.data_loader import load_products, load_units
from app.config import settings

from typing import Iterable, Optional
from app.models import Product


def build_prompt(products: Optional[Iterable[Product]] = None) -> str:
    """Формирует text-prefix для Vision-запроса под индонезийские накладные."""
    if products is None:
        products = load_products()
    # Ограничиваем количество товаров в промпте
    max_products = getattr(settings, "MAX_PRODUCTS_IN_PROMPT", 100)
    sorted_products = sorted(products, key=lambda p: p.alias)[:max_products]
    aliases = [p.alias for p in sorted_products]
    units = load_units()

    lines = [
        "# INSTRUCTION FOR INVOICE RECOGNITION (INDONESIA)",
        "",
        "## CONTEXT:",
        "The image is a photo of an Indonesian invoice, often on pink colored paper, possibly handwritten or printed, sometimes at an angle. The invoice may be in Indonesian or English. Ignore background color, shadows, and noise. Focus on extracting all relevant data, even if the text is unclear.",
        "You are an OCR system for Indonesian invoices. Your task is to extract all information in structured JSON, with all field names and values in English (translate if needed).",
        "All prices are in Indonesian Rupiah (IDR).",
        "",
        "## ALLOWED PRODUCTS (CHOOSE ONLY FROM THIS LIST):",
        *[f"- {name}" for name in sorted(set(aliases))],
        "",
        "## ALLOWED UNITS:",
        *[f"- {u}" for u in units],
        "",
        "## RULES:",
        "1. EXTRACT ONLY products that clearly appear on the invoice image - NEVER invent or hallucinate items.",
        "2. ONLY include products from the ALLOWED PRODUCTS list that EXACTLY match what's visible on the invoice.",
        "3. If you cannot find an exact match in the allowed list for a product on the invoice, DO NOT include it.",
        "4. If you're uncertain about a product name, DO NOT guess - only include products you are confident about.",
        "5. NEVER return random products from the allowed list - only return what is actually visible in the image.",
        "6. Number format: prices are integers (no decimals), quantity may be fractional.",
        "7. All prices must be in IDR (Indonesian Rupiah).",
        "8. Return only pure JSON, no explanations or markdown formatting.",
        "",
        "## RESPONSE FORMAT:",
        "{",
        "  \"supplier\": string | null,  // Supplier name from the invoice or null",
        "  \"date\": string | null,      // Invoice date in YYYY-MM-DD or null",
        "  \"positions\": [              // List of items",
        "    {",
        "      \"name\": string,         // Product name (STRICTLY from the allowed list and MUST be visible on invoice)",
        "      \"qty\": number,          // Quantity",
        "      \"unit\": string,         // Unit",
        "      \"price\": number | null, // Price per unit in IDR or null",
        "      \"total_price\": number | null // Total price for the item in IDR or null",
        "    }",
        "  ],",
        "  \"total_price\": number | null // Total invoice amount in IDR or null",
        "}",
    ]
    return "\n".join(lines)
