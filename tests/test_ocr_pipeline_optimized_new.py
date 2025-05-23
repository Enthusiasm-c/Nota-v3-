"""
Тесты для app/ocr_pipeline_optimized.py - оптимизированный OCR pipeline
"""

import asyncio
import hashlib
import json
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import numpy as np

from app.ocr_pipeline_optimized import (
    OCRPipelineOptimized,
    MAX_PARALLEL_CELLS,
    GPT4O_CONFIDENCE_THRESHOLD,
    CACHE_TTL,
    SMALL_CELL_SIZE_THRESHOLD
)


@pytest.fixture
def mock_image_bytes():
    """Фикстура для мокирования байтов изображения"""
    return b"fake_image_data_for_testing"


@pytest.fixture
def sample_cells():
    """Фикстура для примера ячеек"""
    return [
        {
            "image": np.zeros((20, 20, 3), dtype=np.uint8),
            "row": 0,
            "col": 0,
            "bbox": [0, 0, 20, 20]
        },
        {
            "image": np.zeros((20, 20, 3), dtype=np.uint8),
            "row": 0,
            "col": 1,
            "bbox": [20, 0, 40, 20]
        },
        {
            "image": np.zeros((20, 20, 3), dtype=np.uint8),
            "row": 1,
            "col": 0,
            "bbox": [0, 20, 20, 40]
        }
    ]


@pytest.fixture
def pipeline():
    """Фикстура для OCR pipeline"""
    with patch('app.ocr_pipeline_optimized.get_detector') as mock_detector:
        with patch('app.ocr_pipeline_optimized.ValidationPipeline') as mock_validation:
            with patch('app.ocr_pipeline_optimized.PaddleOCR') as mock_paddle:
                mock_detector.return_value = Mock()
                mock_validation.return_value = Mock()
                mock_paddle.return_value = Mock()
                return OCRPipelineOptimized()


class TestOCRPipelineOptimized:
    """Тесты для класса OCRPipelineOptimized"""

    def test_init_default_parameters(self):
        """Тест инициализации с параметрами по умолчанию"""
        with patch('app.ocr_pipeline_optimized.get_detector') as mock_detector:
            with patch('app.ocr_pipeline_optimized.ValidationPipeline') as mock_validation:
                with patch('app.ocr_pipeline_optimized.PaddleOCR') as mock_paddle:
                    mock_detector.return_value = Mock()
                    mock_validation.return_value = Mock()
                    mock_paddle.return_value = Mock()
                    
                    pipeline = OCRPipelineOptimized()
                    
                    assert pipeline.low_conf_threshold == GPT4O_CONFIDENCE_THRESHOLD
                    assert pipeline.fallback_to_vision is True
                    assert pipeline._metrics["total_cells"] == 0

    def test_init_custom_parameters(self):
        """Тест инициализации с кастомными параметрами"""
        with patch('app.ocr_pipeline_optimized.get_detector') as mock_detector:
            with patch('app.ocr_pipeline_optimized.ValidationPipeline') as mock_validation:
                with patch('app.ocr_pipeline_optimized.PaddleOCR') as mock_paddle:
                    mock_detector.return_value = Mock()
                    mock_validation.return_value = Mock()
                    mock_paddle.return_value = Mock()
                    
                    pipeline = OCRPipelineOptimized(
                        table_detector_method="custom",
                        paddle_ocr_lang="ru",
                        fallback_to_vision=False
                    )
                    
                    assert pipeline.fallback_to_vision is False
                    mock_detector.assert_called_with(method="custom")
                    mock_paddle.assert_called_with(use_angle_cls=True, lang="ru", show_log=False)

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.cache_get')
    @patch('app.ocr_pipeline_optimized.prepare_for_ocr')
    async def test_process_image_cache_hit(self, mock_prepare, mock_cache_get, pipeline, mock_image_bytes):
        """Тест обработки изображения с попаданием в кеш"""
        # Мокируем кешированный результат
        cached_result = {
            "status": "success",
            "lines": [{"name": "Test Item", "qty": 1}],
            "cached": True
        }
        mock_cache_get.return_value = cached_result
        
        result = await pipeline.process_image(mock_image_bytes, ["en"])
        
        assert result == cached_result
        assert pipeline._metrics["cache_hits"] == 1
        mock_cache_get.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.cache_get')
    @patch('app.ocr_pipeline_optimized.cache_set')
    @patch('app.ocr_pipeline_optimized.prepare_for_ocr')
    @patch('app.ocr_pipeline_optimized.get_detector')
    async def test_process_image_success_path(self, mock_get_detector, mock_prepare, mock_cache_set, mock_cache_get, pipeline, mock_image_bytes, sample_cells):
        """Тест успешной обработки изображения"""
        # Настройка моков
        mock_cache_get.return_value = None  # Cache miss
        mock_prepare.return_value = mock_image_bytes
        
        mock_detector = Mock()
        mock_detector.extract_cells.return_value = sample_cells
        mock_get_detector.return_value = mock_detector
        
        # Мокируем _process_cells
        expected_lines = [
            {"name": "Test Item", "qty": 1, "price": 100}
        ]
        pipeline._process_cells = AsyncMock(return_value=expected_lines)
        
        # Мокируем валидацию
        validated_result = {
            "status": "success",
            "lines": expected_lines,
            "accuracy": 0.8,
            "issues": []
        }
        pipeline.validation_pipeline.validate.return_value = validated_result
        
        result = await pipeline.process_image(mock_image_bytes, ["en"])
        
        assert result["status"] == "success"
        assert result["lines"] == expected_lines
        assert "timing" in result
        assert "total_time" in result
        mock_cache_set.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.cache_get')
    @patch('app.ocr_pipeline_optimized.prepare_for_ocr')
    @patch('app.ocr_pipeline_optimized.get_detector')
    async def test_process_image_table_detection_error_with_fallback(self, mock_get_detector, mock_prepare, mock_cache_get, pipeline, mock_image_bytes):
        """Тест обработки ошибки детекции таблицы с fallback на OpenAI Vision"""
        # Настройка моков
        mock_cache_get.return_value = None
        mock_prepare.return_value = mock_image_bytes
        
        mock_detector = Mock()
        mock_detector.extract_cells.side_effect = Exception("Table detection failed")
        mock_get_detector.return_value = mock_detector
        
        # Мокируем OpenAI Vision fallback
        vision_result = {
            "status": "success",
            "lines": [{"name": "Vision Item", "qty": 2}],
            "accuracy": 0.9
        }
        pipeline._process_with_openai_vision = AsyncMock(return_value=vision_result)
        
        # Мокируем валидацию
        validated_result = {**vision_result, "validated": True}
        pipeline.validation_pipeline.validate.return_value = validated_result
        
        result = await pipeline.process_image(mock_image_bytes, ["en"])
        
        assert result["status"] == "success"
        assert result["used_fallback"] is True
        assert "table_detection_error" in result["timing"]
        pipeline._process_with_openai_vision.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.cache_get')
    @patch('app.ocr_pipeline_optimized.prepare_for_ocr')
    @patch('app.ocr_pipeline_optimized.get_detector')
    async def test_process_image_table_detection_error_no_fallback(self, mock_get_detector, mock_prepare, mock_cache_get, mock_image_bytes):
        """Тест обработки ошибки детекции таблицы без fallback"""
        # Создаем pipeline без fallback
        with patch('app.ocr_pipeline_optimized.ValidationPipeline'):
            with patch('app.ocr_pipeline_optimized.PaddleOCR'):
                pipeline = OCRPipelineOptimized(fallback_to_vision=False)
        
        mock_cache_get.return_value = None
        mock_prepare.return_value = mock_image_bytes
        
        mock_detector = Mock()
        mock_detector.extract_cells.side_effect = Exception("Table detection failed")
        mock_get_detector.return_value = mock_detector
        
        result = await pipeline.process_image(mock_image_bytes, ["en"])
        
        assert result["status"] == "error"
        assert "Table detection failed" in result["message"]

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.cache_get')
    @patch('app.ocr_pipeline_optimized.prepare_for_ocr')
    async def test_process_image_optimization_error_non_critical(self, mock_prepare, mock_cache_get, pipeline, mock_image_bytes):
        """Тест обработки некритичной ошибки оптимизации изображения"""
        mock_cache_get.return_value = None
        mock_prepare.side_effect = Exception("Optimization failed")
        
        # Мокируем успешную обработку с оригинальным изображением
        with patch('app.ocr_pipeline_optimized.get_detector') as mock_get_detector:
            mock_detector = Mock()
            mock_detector.extract_cells.return_value = []
            mock_get_detector.return_value = mock_detector
            
            pipeline._process_cells = AsyncMock(return_value=[])
            pipeline.validation_pipeline.validate.return_value = {
                "status": "success",
                "lines": []
            }
            
            result = await pipeline.process_image(mock_image_bytes, ["en"])
            
            assert result["status"] == "success"

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.call_openai_ocr_async')
    async def test_process_with_openai_vision_success(self, mock_openai_ocr, pipeline, mock_image_bytes):
        """Тест успешной обработки через OpenAI Vision"""
        # Мокируем ответ OpenAI
        openai_response = json.dumps({
            "lines": [
                {"name": "Apple", "qty": 5, "unit": "kg", "price": 100, "amount": 500}
            ]
        })
        mock_openai_ocr.return_value = openai_response
        
        result = await pipeline._process_with_openai_vision(mock_image_bytes, ["en"])
        
        assert result["status"] == "success"
        assert len(result["lines"]) == 1
        assert result["lines"][0]["name"] == "Apple"
        assert result["accuracy"] == 0.9

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.call_openai_ocr_async')
    async def test_process_with_openai_vision_positions_format(self, mock_openai_ocr, pipeline, mock_image_bytes):
        """Тест обработки OpenAI Vision с форматом positions"""
        # Мокируем ответ OpenAI в формате positions
        openai_response = json.dumps({
            "positions": [
                {"name": "Banana", "qty": 3, "unit": "pcs", "price": 50, "total_price": 150}
            ]
        })
        mock_openai_ocr.return_value = openai_response
        
        result = await pipeline._process_with_openai_vision(mock_image_bytes, ["en"])
        
        assert result["status"] == "success"
        assert len(result["lines"]) == 1
        assert result["lines"][0]["name"] == "Banana"
        assert result["lines"][0]["amount"] == 150

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.call_openai_ocr_async')
    async def test_process_with_openai_vision_retry_logic(self, mock_openai_ocr, pipeline, mock_image_bytes):
        """Тест логики повторных попыток в OpenAI Vision"""
        # Первый вызов неудачный, второй успешный
        mock_openai_ocr.side_effect = [
            Exception("API Error"),
            json.dumps({"lines": []})
        ]
        
        result = await pipeline._process_with_openai_vision(mock_image_bytes, ["en"])
        
        assert result["status"] == "success"
        assert mock_openai_ocr.call_count == 2

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.call_openai_ocr_async')
    async def test_process_with_openai_vision_all_retries_fail(self, mock_openai_ocr, pipeline, mock_image_bytes):
        """Тест случая, когда все попытки OpenAI Vision неудачны"""
        mock_openai_ocr.side_effect = Exception("Persistent API Error")
        
        result = await pipeline._process_with_openai_vision(mock_image_bytes, ["en"])
        
        assert result["status"] == "error"
        assert "Persistent API Error" in result["message"]

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.call_openai_ocr_async')
    async def test_process_with_openai_vision_invalid_json(self, mock_openai_ocr, pipeline, mock_image_bytes):
        """Тест обработки невалидного JSON от OpenAI Vision"""
        mock_openai_ocr.return_value = "invalid json response"
        
        result = await pipeline._process_with_openai_vision(mock_image_bytes, ["en"])
        
        assert result["status"] == "error"
        assert "Failed to parse OpenAI Vision result" in result["message"]

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.prepare_cell_image')
    async def test_ocr_cell_too_small(self, mock_prepare_cell, pipeline):
        """Тест обработки слишком маленькой ячейки"""
        mock_prepare_cell.return_value = None
        
        cell = {"image": np.zeros((5, 5, 3), dtype=np.uint8)}
        
        result = await pipeline._ocr_cell(cell)
        
        assert result["text"] == ""
        assert result["confidence"] == 0.0
        assert result["error"] == "too_small"

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.prepare_cell_image')
    @patch('app.ocr_pipeline_optimized.process_cell_with_gpt4o')
    async def test_ocr_cell_small_uses_gpt4o(self, mock_gpt4o, mock_prepare_cell, pipeline):
        """Тест использования GPT-4o для маленьких ячеек"""
        mock_prepare_cell.return_value = np.zeros((10, 10, 3), dtype=np.uint8)  # Маленькое изображение
        mock_gpt4o.return_value = ("123", 0.95)
        
        cell = {"image": np.zeros((10, 10, 3), dtype=np.uint8)}
        
        result = await pipeline._ocr_cell(cell)
        
        assert result["text"] == "123"
        assert result["confidence"] == 0.95
        assert result["used_gpt4o"] is True

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.prepare_cell_image')
    async def test_ocr_cell_paddle_success(self, mock_prepare_cell, pipeline):
        """Тест успешной обработки ячейки с PaddleOCR"""
        mock_prepare_cell.return_value = np.zeros((30, 30, 3), dtype=np.uint8)
        
        # Мокируем результат PaddleOCR - упрощенный формат для избежания ошибок парсинга
        pipeline.paddle_ocr.ocr.return_value = [[(None, ("Test Text", 0.9))]]
        
        cell = {"image": np.zeros((30, 30, 3), dtype=np.uint8)}
        
        result = await pipeline._ocr_cell(cell)
        
        assert result["text"] == "Test Text"
        assert result["confidence"] == 0.9
        assert result["used_gpt4o"] is False

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.prepare_cell_image')
    @patch('app.ocr_pipeline_optimized.process_cell_with_gpt4o')
    async def test_ocr_cell_low_confidence_fallback(self, mock_gpt4o, mock_prepare_cell, pipeline):
        """Тест fallback на GPT-4o при низкой уверенности PaddleOCR"""
        mock_prepare_cell.return_value = np.zeros((30, 30, 3), dtype=np.uint8)
        
        # PaddleOCR возвращает низкую уверенность
        pipeline.paddle_ocr.ocr.return_value = [[(None, ("Low Conf", 0.3))]]
        
        # GPT-4o возвращает лучший результат
        mock_gpt4o.return_value = ("High Conf", 0.95)
        
        cell = {"image": np.zeros((30, 30, 3), dtype=np.uint8)}
        
        result = await pipeline._ocr_cell(cell)
        
        assert result["text"] == "High Conf"
        assert result["confidence"] == 0.95
        assert result["used_gpt4o"] is True

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.prepare_cell_image')
    async def test_ocr_cell_paddle_error(self, mock_prepare_cell, pipeline):
        """Тест обработки ошибки PaddleOCR"""
        mock_prepare_cell.return_value = np.zeros((30, 30, 3), dtype=np.uint8)
        
        # PaddleOCR выбрасывает исключение
        pipeline.paddle_ocr.ocr.side_effect = Exception("PaddleOCR error")
        
        # Мокируем GPT-4o fallback
        with patch('app.ocr_pipeline_optimized.process_cell_with_gpt4o') as mock_gpt4o:
            mock_gpt4o.return_value = ("Fallback Text", 0.8)
            
            cell = {"image": np.zeros((30, 30, 3), dtype=np.uint8)}
            
            result = await pipeline._ocr_cell(cell)
            
            assert result["text"] == "Fallback Text"
            assert result["used_gpt4o"] is True

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.prepare_cell_image')
    async def test_ocr_cell_digits_only(self, mock_prepare_cell, pipeline):
        """Тест обработки ячеек с только цифрами"""
        mock_prepare_cell.return_value = np.zeros((30, 30, 3), dtype=np.uint8)
        
        # PaddleOCR возвращает только цифры
        pipeline.paddle_ocr.ocr.return_value = [[(None, ("  123  ", 0.9))]]
        
        cell = {"image": np.zeros((30, 30, 3), dtype=np.uint8)}
        
        result = await pipeline._ocr_cell(cell)
        
        assert result["text"] == "123"  # Должно быть обрезано
        assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.build_lines_from_cells')
    async def test_process_cells_empty_list(self, mock_build_lines, pipeline):
        """Тест обработки пустого списка ячеек"""
        mock_build_lines.return_value = []
        
        result = await pipeline._process_cells([], ["en"])
        
        assert result == []
        assert pipeline._metrics["total_cells"] == 0
        assert pipeline._metrics["gpt4o_percent"] == 0

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.build_lines_from_cells')
    async def test_process_cells_parallel_processing(self, mock_build_lines, pipeline, sample_cells):
        """Тест параллельной обработки ячеек"""
        mock_build_lines.return_value = [{"name": "Test", "qty": 1}]
        
        # Мокируем _ocr_cell для возврата результатов
        async def mock_ocr_cell(cell):
            return {**cell, "text": "Test", "confidence": 0.9, "used_gpt4o": False}
        
        pipeline._ocr_cell = mock_ocr_cell
        
        result = await pipeline._process_cells(sample_cells, ["en"])
        
        assert len(result) == 1
        assert pipeline._metrics["total_cells"] == 3
        mock_build_lines.assert_called_once()

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.build_lines_from_cells')
    async def test_process_cells_gpt4o_usage_tracking(self, mock_build_lines, pipeline, sample_cells):
        """Тест отслеживания использования GPT-4o"""
        mock_build_lines.return_value = []
        
        # Мокируем _ocr_cell для возврата результатов с разным использованием GPT-4o
        call_count = 0
        async def mock_ocr_cell(cell):
            nonlocal call_count
            call_count += 1
            used_gpt = call_count <= 2  # Первые 2 используют GPT-4o
            return {**cell, "text": "Test", "confidence": 0.9, "used_gpt4o": used_gpt}
        
        pipeline._ocr_cell = mock_ocr_cell
        
        await pipeline._process_cells(sample_cells, ["en"])
        
        assert pipeline._metrics["gpt4o_count"] == 2
        assert pipeline._metrics["gpt4o_percent"] == 2/3 * 100  # 66.67%

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.build_lines_from_cells')
    async def test_process_cells_parallel_error_fallback(self, mock_build_lines, pipeline):
        """Тест fallback на последовательную обработку при ошибке параллельной"""
        mock_build_lines.return_value = []
        
        # Создаем ячейки, которые вызовут ошибку при параллельной обработке
        problem_cells = [
            {"image": np.zeros((20, 20, 3), dtype=np.uint8), "problem": True}
            for _ in range(5)
        ]
        
        # Мокируем _ocr_cell для генерации ошибки в asyncio.gather
        async def mock_ocr_cell_error(cell):
            if cell.get("problem"):
                raise Exception("Parallel processing error")
            return {**cell, "text": "OK", "confidence": 0.9}
        
        # Заменяем _ocr_cell для генерации ошибки при первом вызове
        original_ocr_cell = pipeline._ocr_cell
        pipeline._ocr_cell = mock_ocr_cell_error
        
        # Мокируем asyncio.gather для генерации ошибки
        with patch('asyncio.gather') as mock_gather:
            mock_gather.side_effect = Exception("Gather failed")
            
            # Создаем новый _ocr_cell для последовательной обработки
            async def sequential_ocr_cell(cell):
                return {**cell, "text": "Sequential", "confidence": 0.8, "used_gpt4o": False}
            
            # Частичный мок для последовательной обработки
            with patch.object(pipeline, '_ocr_cell', sequential_ocr_cell):
                result = await pipeline._process_cells(problem_cells, ["en"])
                
                assert result == []  # build_lines_from_cells returns []

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.build_lines_from_cells')
    async def test_process_cells_all_empty_text_recovery(self, mock_build_lines, pipeline):
        """Тест восстановления текста из структуры при пустых ячейках"""
        mock_build_lines.return_value = []
        
        # Создаем ячейки с пустым текстом, но со структурой
        cells_with_structure = [
            {
                "image": np.zeros((20, 20, 3), dtype=np.uint8),
                "structure": {"text": "Hidden Text 1"}
            },
            {
                "image": np.zeros((20, 20, 3), dtype=np.uint8),
                "structure": {"text": "Hidden Text 2"}
            },
            {
                "image": np.zeros((20, 20, 3), dtype=np.uint8),
                "structure": {}  # Без текста в структуре
            }
        ]
        
        # Мокируем _ocr_cell для возврата пустого текста
        async def mock_ocr_cell_empty(cell):
            return {**cell, "text": "", "confidence": 0.0, "used_gpt4o": False}
        
        pipeline._ocr_cell = mock_ocr_cell_empty
        
        result = await pipeline._process_cells(cells_with_structure, ["en"])
        
        # Функция должна попытаться восстановить текст из структуры
        assert result == []


class TestPipelineMetrics:
    """Тесты для метрик pipeline"""

    def test_get_metrics_initial(self, pipeline):
        """Тест получения начальных метрик"""
        metrics = pipeline.get_metrics()
        
        assert "gpt4o_percent" in metrics
        assert "total_cells" in metrics
        assert "cache_hits" in metrics
        assert metrics["gpt4o_percent"] == 0
        assert metrics["total_cells"] == 0

    @pytest.mark.asyncio
    async def test_metrics_update_during_processing(self, pipeline, sample_cells):
        """Тест обновления метрик во время обработки"""
        with patch('app.ocr_pipeline_optimized.build_lines_from_cells') as mock_build_lines:
            mock_build_lines.return_value = []
            
            # Мокируем _ocr_cell
            async def mock_ocr_cell(cell):
                return {**cell, "text": "Test", "confidence": 0.9, "used_gpt4o": True}
            
            pipeline._ocr_cell = mock_ocr_cell
            
            await pipeline._process_cells(sample_cells, ["en"])
            
            metrics = pipeline.get_metrics()
            assert metrics["total_cells"] == 3
            assert metrics["gpt4o_count"] == 3
            assert metrics["gpt4o_percent"] == 100.0


class TestConstants:
    """Тесты для констант модуля"""

    def test_constants_defined(self):
        """Тест определения констант"""
        assert MAX_PARALLEL_CELLS == 10
        assert GPT4O_CONFIDENCE_THRESHOLD == 0.75
        assert CACHE_TTL == 24 * 60 * 60
        assert SMALL_CELL_SIZE_THRESHOLD == 15


class TestErrorHandling:
    """Тесты для обработки ошибок"""

    @pytest.mark.asyncio
    async def test_critical_error_in_ocr_cell(self, pipeline):
        """Тест обработки критической ошибки в _ocr_cell"""
        cell = {"image": np.zeros((20, 20, 3), dtype=np.uint8)}
        
        # Мокируем prepare_cell_image для генерации ошибки
        with patch('app.ocr_pipeline_optimized.prepare_cell_image') as mock_prepare:
            mock_prepare.side_effect = Exception("Critical error")
            
            result = await pipeline._ocr_cell(cell)
            
            assert result["text"] == ""
            assert result["confidence"] == 0.0
            assert result["used_gpt4o"] is False
            assert "error" in result

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.cache_get')
    @patch('app.ocr_pipeline_optimized.prepare_for_ocr')
    async def test_general_processing_error(self, mock_prepare, mock_cache_get, pipeline, mock_image_bytes):
        """Тест обработки общей ошибки обработки"""
        mock_cache_get.return_value = None
        mock_prepare.return_value = mock_image_bytes
        
        # Создаем pipeline без fallback чтобы избежать OpenAI вызовов
        with patch('app.ocr_pipeline_optimized.ValidationPipeline'):
            with patch('app.ocr_pipeline_optimized.PaddleOCR'):
                error_pipeline = OCRPipelineOptimized(fallback_to_vision=False)
        
        # Мокируем get_detector для генерации критической ошибки
        with patch('app.ocr_pipeline_optimized.get_detector') as mock_get_detector:
            mock_get_detector.side_effect = Exception("Critical pipeline error")
            
            result = await error_pipeline.process_image(mock_image_bytes, ["en"])
            
            assert result["status"] == "error"
            assert "Critical pipeline error" in result["message"]
            assert "total_time" in result


class TestCacheIntegration:
    """Тесты для интеграции с кешем"""

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.cache_get')
    async def test_cache_disabled(self, mock_cache_get, pipeline, mock_image_bytes):
        """Тест отключения кеша"""
        with patch('app.ocr_pipeline_optimized.prepare_for_ocr') as mock_prepare:
            with patch('app.ocr_pipeline_optimized.get_detector') as mock_get_detector:
                mock_prepare.return_value = mock_image_bytes
                mock_detector = Mock()
                mock_detector.extract_cells.return_value = []
                mock_get_detector.return_value = mock_detector
                
                pipeline._process_cells = AsyncMock(return_value=[])
                pipeline.validation_pipeline.validate.return_value = {
                    "status": "success",
                    "lines": []
                }
                
                result = await pipeline.process_image(mock_image_bytes, ["en"], use_cache=False)
                
                # Кеш не должен быть вызван
                mock_cache_get.assert_not_called()

    @pytest.mark.asyncio
    @patch('app.ocr_pipeline_optimized.cache_get')
    @patch('app.ocr_pipeline_optimized.cache_set')
    async def test_cache_error_handling(self, mock_cache_set, mock_cache_get, pipeline, mock_image_bytes):
        """Тест обработки ошибок кеша"""
        mock_cache_get.return_value = None
        mock_cache_set.side_effect = Exception("Cache error")
        
        with patch('app.ocr_pipeline_optimized.prepare_for_ocr') as mock_prepare:
            with patch('app.ocr_pipeline_optimized.get_detector') as mock_get_detector:
                mock_prepare.return_value = mock_image_bytes
                mock_detector = Mock()
                mock_detector.extract_cells.return_value = []
                mock_get_detector.return_value = mock_detector
                
                pipeline._process_cells = AsyncMock(return_value=[])
                pipeline.validation_pipeline.validate.return_value = {
                    "status": "success",
                    "lines": []
                }
                
                # Не должно падать при ошибке кеша
                result = await pipeline.process_image(mock_image_bytes, ["en"])
                
                assert result["status"] == "success" 
 