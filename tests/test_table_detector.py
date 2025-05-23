import os
from unittest.mock import MagicMock, patch

import pytest

from app.detectors.table.factory import get_detector
from app.detectors.table.paddle_detector import PaddleTableDetector


class TestTableDetector:
    """Тесты для модуля детекции таблиц."""

    def test_detector_factory(self):
        """Тест фабрики детекторов."""
        detector = get_detector("paddle")
        assert isinstance(detector, PaddleTableDetector)

        # Тест дефолтного значения
        detector = get_detector()
        assert isinstance(detector, PaddleTableDetector)

        # Тест неизвестного метода
        detector = get_detector("unknown")
        assert isinstance(detector, PaddleTableDetector)

    @pytest.mark.skipif(not os.environ.get("TEST_PADDLEOCR"), reason="PaddleOCR tests disabled")
    def test_paddle_detector_init(self):
        """Тест инициализации PaddleTableDetector."""
        detector = PaddleTableDetector()
        assert detector.structure_engine is not None

    @patch("app.detectors.table.paddle_detector.PaddleTableDetector.detect")
    def test_paddle_detector_detect_called(self, mock_detect):
        """Тест вызова метода detect."""
        mock_detect.return_value = {"tables": []}

        detector = PaddleTableDetector()
        image_bytes = b"fake_image_data"
        result = detector.detect(image_bytes)

        mock_detect.assert_called_once_with(image_bytes)
        assert "tables" in result

    @patch("app.detectors.table.paddle_detector.PaddleTableDetector.extract_cells")
    def test_paddle_detector_extract_cells_called(self, mock_extract_cells):
        """Тест вызова метода extract_cells."""
        mock_extract_cells.return_value = []

        detector = PaddleTableDetector()
        image_bytes = b"fake_image_data"
        cells = detector.extract_cells(image_bytes)

        mock_extract_cells.assert_called_once_with(image_bytes)
        assert isinstance(cells, list)


# Проверка на наличие тестовых данных
@pytest.mark.skipif(
    not os.path.exists("tests/fixtures/sample_invoice.png"), reason="Sample invoice not found"
)
class TestTableDetectorWithFixtures:
    """Тесты с реальными данными."""

    def test_detect_with_fixture(self):
        """Тест обнаружения таблицы на реальном изображении."""
        # Загружаем тестовое изображение
        fixture_path = "tests/fixtures/sample_invoice.png"
        with open(fixture_path, "rb") as f:
            image_bytes = f.read()

        # Вызываем детектор через мок
        with patch("paddleocr.PPStructure") as MockPPStructure:
            mock_instance = MagicMock()
            mock_instance.return_value = [
                {
                    "type": "table",
                    "bbox": [10, 20, 300, 400],
                    "res": [
                        {"bbox": [10, 20, 100, 50], "text": "Header 1"},
                        {"bbox": [110, 20, 200, 50], "text": "Header 2"},
                    ],
                }
            ]
            MockPPStructure.return_value = mock_instance

            # Создаем детектор и тестируем
            detector = PaddleTableDetector()
            result = detector.detect(image_bytes)

            assert "tables" in result
            assert len(result["tables"]) == 1
            assert "bbox" in result["tables"][0]
            assert "cells" in result["tables"][0]
            assert len(result["tables"][0]["cells"]) == 2


def test_detect_tables_success():
    fake_ppstructure = MagicMock()
    fake_ppstructure.return_value = [
        {"type": "table", "bbox": [0, 0, 10, 10], "res": [{"bbox": [0, 0, 5, 5], "text": "cell1"}]},
        {"type": "other", "bbox": [0, 0, 10, 10], "res": []},
    ]
    detector = PaddleTableDetector()
    detector.structure_engine = fake_ppstructure
    image_bytes = b"fake_image"
    with patch("PIL.Image.open") as mock_open:
        mock_img = MagicMock()
        mock_img.convert.return_value = mock_img
        mock_img.width = 10
        mock_img.height = 10
        mock_img.crop.return_value = mock_img
        mock_open.return_value = mock_img
        result = detector.detect(image_bytes)
        assert "tables" in result
        assert len(result["tables"]) == 1
        assert result["tables"][0]["bbox"] == [0, 0, 10, 10]
        assert isinstance(result["tables"][0]["cells"], list)


def test_detect_tables_incorrect_result():
    fake_ppstructure = MagicMock(return_value="not_a_list")
    detector = PaddleTableDetector()
    detector.structure_engine = fake_ppstructure
    image_bytes = b"fake_image"
    with patch("PIL.Image.open") as mock_open:
        mock_img = MagicMock()
        mock_img.convert.return_value = mock_img
        mock_open.return_value = mock_img
        result = detector.detect(image_bytes)
        assert result == {"tables": []}


def test_detect_no_structure_engine():
    detector = PaddleTableDetector()
    detector.structure_engine = None
    with pytest.raises(RuntimeError):
        detector.detect(b"fake_image")


def test_extract_cells_incorrect_result():
    fake_ppstructure = MagicMock(return_value="not_a_list")
    detector = PaddleTableDetector()
    detector.structure_engine = fake_ppstructure
    image_bytes = b"fake_image"
    with patch("PIL.Image.open") as mock_open:
        mock_img = MagicMock()
        mock_img.convert.return_value = mock_img
        mock_open.return_value = mock_img
        result = detector.extract_cells(image_bytes)
        assert result == []


def test_extract_no_structure_engine():
    detector = PaddleTableDetector()
    detector.structure_engine = None
    with pytest.raises(RuntimeError):
        detector.extract_cells(b"fake_image")
