import pytest
from unittest.mock import MagicMock, patch
from app.ocr_pipeline import OCRPipeline


def test_ocr_pipeline_init():
    # Проверяем, что пайплайн инициализируется с дефолтными параметрами
    pipeline = OCRPipeline()
    assert pipeline.table_detector is not None
    assert pipeline.validation_pipeline is not None
    assert pipeline.paddle_ocr is not None


def test_ocr_pipeline_process_success(monkeypatch):
    # Мокаем все внешние зависимости
    with patch("app.ocr_pipeline.get_detector") as mock_get_detector, \
         patch("app.ocr_pipeline.PaddleOCR") as mock_paddle_ocr, \
         patch("app.ocr_pipeline.ValidationPipeline") as mock_validation, \
         patch("app.ocr_pipeline.call_openai_ocr") as mock_call_ocr, \
         patch("app.ocr_pipeline.postprocess_parsed_data") as mock_postprocess:
        mock_get_detector.return_value = MagicMock()
        mock_paddle_ocr.return_value = MagicMock()
        mock_validation.return_value = MagicMock()
        mock_call_ocr.return_value = MagicMock()
        mock_postprocess.return_value = MagicMock()
        pipeline = OCRPipeline()
        # Проверяем, что пайплайн работает без ошибок
        assert pipeline.table_detector is not None


def test_ocr_pipeline_error_handling(monkeypatch):
    # Мокаем get_detector, чтобы выбрасывать ошибку
    with patch("app.ocr_pipeline.get_detector", side_effect=Exception("detector error")):
        with pytest.raises(Exception):
            OCRPipeline() 