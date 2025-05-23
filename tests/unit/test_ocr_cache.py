import pytest
from unittest.mock import MagicMock, patch
import pickle
import hashlib

from app.utils.ocr_cache import (
    get_from_cache,
    save_to_cache,
    get_cache_key,
    clear_expired_cache
)
from app.models import ParsedData, Position

@pytest.fixture
def mock_cache_client():
    """Создает мок для клиента кеша"""
    mock = MagicMock()
    mock.get.return_value = None
    mock.set.return_value = True
    return mock

@pytest.fixture
def sample_parsed_data():
    """Создает образец данных ParsedData для тестов"""
    return ParsedData(
        supplier="Test Supplier",
        date="2025-01-01",
        positions=[
            Position(name="Product 1", qty=2, unit="kg", price=100, total_price=200),
            Position(name="Product 2", qty=1, unit="pcs", price=50, total_price=50)
        ],
        total_price=250
    )

@pytest.fixture
def sample_image_bytes():
    """Создает тестовые байты изображения"""
    return b"test_image_bytes_123"

def test_get_cache_key(sample_image_bytes):
    """Тест функции создания ключа кеша"""
    # Проверяем, что ключ создается корректно
    key = get_cache_key(sample_image_bytes)
    
    # Ключ должен быть строкой
    assert isinstance(key, str)
    
    # Ключ должен быть SHA256 хешем
    expected_key = hashlib.sha256(sample_image_bytes).hexdigest()
    assert key == expected_key
    
    # Проверяем, что для одинаковых изображений ключи совпадают
    assert get_cache_key(sample_image_bytes) == get_cache_key(sample_image_bytes)
    
    # Проверяем, что для разных изображений ключи разные
    assert get_cache_key(sample_image_bytes) != get_cache_key(b"different_image")

def test_save_to_cache(mock_cache_client, sample_parsed_data, sample_image_bytes):
    """Тест сохранения данных в кеш"""
    with patch('app.utils.ocr_cache.redis_client', mock_cache_client):
        # Сохраняем данные в кеш
        save_to_cache(sample_image_bytes, sample_parsed_data)
        
        # Проверяем, что кеш-клиент был вызван с правильными параметрами
        mock_cache_client.set.assert_called_once()
        
        # Проверяем ключ
        call_args = mock_cache_client.set.call_args[0]
        assert call_args[0] == get_cache_key(sample_image_bytes)
        
        # Проверяем, что в кеш сохраняются сериализованные данные
        serialized_data = pickle.dumps(sample_parsed_data)
        assert call_args[1] == serialized_data
        
        # Проверяем, что установлено время жизни кеша
        assert 'ex' in mock_cache_client.set.call_args[1]

def test_get_from_cache_hit(mock_cache_client, sample_parsed_data, sample_image_bytes):
    """Тест получения данных из кеша при наличии данных (cache hit)"""
    # Мокаем наличие данных в кеше
    serialized_data = pickle.dumps(sample_parsed_data)
    mock_cache_client.get.return_value = serialized_data
    
    with patch('app.utils.ocr_cache.redis_client', mock_cache_client):
        # Получаем данные из кеша
        result = get_from_cache(sample_image_bytes)
        
        # Проверяем, что кеш-клиент был вызван с правильным ключом
        mock_cache_client.get.assert_called_once_with(get_cache_key(sample_image_bytes))
        
        # Проверяем, что данные получены и десериализованы правильно
        assert result is not None
        assert isinstance(result, ParsedData)
        assert result.supplier == sample_parsed_data.supplier
        assert result.date == sample_parsed_data.date
        assert len(result.positions) == len(sample_parsed_data.positions)
        assert result.total_price == sample_parsed_data.total_price

def test_get_from_cache_miss(mock_cache_client, sample_image_bytes):
    """Тест получения данных из кеша при отсутствии данных (cache miss)"""
    # Мокаем отсутствие данных в кеше
    mock_cache_client.get.return_value = None
    
    with patch('app.utils.ocr_cache.redis_client', mock_cache_client):
        # Получаем данные из кеша
        result = get_from_cache(sample_image_bytes)
        
        # Проверяем, что кеш-клиент был вызван с правильным ключом
        mock_cache_client.get.assert_called_once_with(get_cache_key(sample_image_bytes))
        
        # Проверяем, что результат None
        assert result is None

def test_get_from_cache_error(mock_cache_client, sample_image_bytes):
    """Тест обработки ошибки при получении данных из кеша"""
    # Мокаем ошибку в кеш-клиенте
    mock_cache_client.get.side_effect = Exception("Redis connection error")
    
    with patch('app.utils.ocr_cache.redis_client', mock_cache_client):
        # Получаем данные из кеша
        result = get_from_cache(sample_image_bytes)
        
        # Проверяем, что кеш-клиент был вызван с правильным ключом
        mock_cache_client.get.assert_called_once_with(get_cache_key(sample_image_bytes))
        
        # Проверяем, что при ошибке возвращается None
        assert result is None

def test_save_to_cache_error(mock_cache_client, sample_parsed_data, sample_image_bytes):
    """Тест обработки ошибки при сохранении данных в кеш"""
    # Мокаем ошибку в кеш-клиенте
    mock_cache_client.set.side_effect = Exception("Redis connection error")
    
    with patch('app.utils.ocr_cache.redis_client', mock_cache_client):
        # Проверяем, что ошибка не распространяется наружу
        try:
            save_to_cache(sample_image_bytes, sample_parsed_data)
            # Если дошли сюда, то исключение не выброшено
            assert True
        except Exception:
            pytest.fail("save_to_cache не должен выбрасывать исключения при ошибках Redis")

def test_clear_expired_cache(mock_cache_client):
    """Тест очистки истекших записей кеша"""
    # Мокаем данные для сканирования
    mock_cache_client.scan_iter.return_value = ["key1", "key2", "key3"]
    
    # Мокаем возвращаемые TTL значения
    mock_cache_client.ttl.side_effect = [-1, 100, 0]
    
    with patch('app.utils.ocr_cache.redis_client', mock_cache_client):
        # Вызываем функцию очистки
        cleared_count = clear_expired_cache()
        
        # Проверяем, что scan_iter был вызван
        mock_cache_client.scan_iter.assert_called_once()
        
        # Проверяем, что ttl был вызван 3 раза (для каждого ключа)
        assert mock_cache_client.ttl.call_count == 3
        
        # Проверяем, что было удалено 2 ключа (с ttl -1 и 0)
        assert mock_cache_client.delete.call_count == 2
        
        # Проверяем, что функция вернула правильное количество удаленных ключей
        assert cleared_count == 2