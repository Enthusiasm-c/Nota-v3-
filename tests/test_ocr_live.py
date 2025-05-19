import os
import pytest
from pathlib import Path
from app.ocr import call_openai_ocr


@pytest.mark.asyncio
@pytest.mark.vcr()
@pytest.mark.skipif("OPENAI_API_KEY" not in os.environ, reason="no key")
async def test_live_ocr():
    img = Path("tests/sample_invoice.jpg").read_bytes()
    result = await call_openai_ocr(img)
    assert getattr(result, "positions", None), "no positions parsed"
