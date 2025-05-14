#!/bin/bash
# Скрипт для тестирования производительности бота после оптимизаций

echo "=== Nota Bot Performance Test ==="
echo "This script will run tests to verify optimizations"
echo ""

# Создаем временную директорию для тестов
TEST_DIR="./test_results"
mkdir -p "$TEST_DIR"

# Функция для запуска бота на короткое время и замера потребления ресурсов
test_startup_time() {
    echo "Testing startup time and resource usage..."
    
    # Запускаем бот с таймингом
    START_TIME=$(date +%s.%N)
    timeout 10 python bot.py --force-restart > "$TEST_DIR/startup_log.txt" 2>&1 &
    BOT_PID=$!
    
    # Ждем 5 секунд для полной инициализации
    sleep 5
    
    # Измеряем использование памяти
    if [ "$(uname)" == "Darwin" ]; then
        # macOS
        MEM_USAGE=$(ps -o rss= -p $BOT_PID | awk '{print $1/1024 " MB"}')
    else
        # Linux
        MEM_USAGE=$(ps -o rss= -p $BOT_PID | awk '{print $1/1024 " MB"}')
    fi
    
    # Останавливаем бот
    kill -SIGINT $BOT_PID 2>/dev/null
    wait $BOT_PID 2>/dev/null
    
    END_TIME=$(date +%s.%N)
    STARTUP_TIME=$(echo "$END_TIME - $START_TIME" | bc)
    
    echo "Startup completed in: $STARTUP_TIME seconds"
    echo "Memory usage: $MEM_USAGE"
    echo ""
    
    echo "Startup Time: $STARTUP_TIME seconds" > "$TEST_DIR/startup_metrics.txt"
    echo "Memory Usage: $MEM_USAGE" >> "$TEST_DIR/startup_metrics.txt"
}

# Функция для тестирования Redis-кеша
test_redis_cache() {
    echo "Testing Redis cache functionality..."
    
    # Проверяем доступность Redis
    if ! command -v redis-cli &> /dev/null || ! redis-cli ping > /dev/null 2>&1; then
        echo "Redis is not available, skipping cache test"
        return
    fi
    
    # Запускаем тест кеша
    python -c "
import time
import sys
from app.utils.redis_cache import cache_set, cache_get, clear_cache

def test_redis():
    print('Testing Redis cache performance...')
    
    # Очищаем кеш перед тестами
    clear_cache()
    
    # Тест скорости записи
    start = time.time()
    for i in range(100):
        cache_set(f'test_key_{i}', f'test_value_{i}', ex=60)
    write_time = time.time() - start
    print(f'Write: 100 items in {write_time:.4f}s ({100/write_time:.1f} items/s)')
    
    # Тест скорости чтения
    start = time.time()
    hits = 0
    for i in range(100):
        val = cache_get(f'test_key_{i}')
        if val == f'test_value_{i}':
            hits += 1
    read_time = time.time() - start
    print(f'Read: 100 items in {read_time:.4f}s ({100/read_time:.1f} items/s)')
    print(f'Cache hit rate: {hits}%')
    
    # Очищаем после теста
    clear_cache()
    
    return True

try:
    test_redis()
except Exception as e:
    print(f'Error testing Redis: {e}')
    sys.exit(1)
" > "$TEST_DIR/redis_test.txt" 2>&1
    
    echo "Redis cache test completed, results in $TEST_DIR/redis_test.txt"
    echo ""
}

# Функция для проверки оптимизированного сопоставления
test_matching() {
    echo "Testing optimized matching performance..."
    
    python -c "
import time
import sys
from app import data_loader
from app.matcher import match_positions
from app.utils.optimized_matcher import async_match_positions
import asyncio

def test_matching():
    print('Testing matching performance...')
    
    # Загружаем продукты
    products = data_loader.load_products('data/base_products.csv')
    print(f'Loaded {len(products)} products')
    
    # Создаем тестовые позиции
    test_positions = [
        {'name': 'Apple', 'qty': 1, 'unit': 'kg'},
        {'name': 'Banana', 'qty': 2, 'unit': 'kg'},
        {'name': 'Orange', 'qty': 3, 'unit': 'kg'},
        {'name': 'Tomato', 'qty': 4, 'unit': 'kg'},
        {'name': 'Cucumber', 'qty': 5, 'unit': 'kg'},
    ]
    
    # Тест стандартного сопоставления
    start = time.time()
    result = match_positions(test_positions, products)
    std_time = time.time() - start
    print(f'Standard matching: {std_time:.4f}s')
    
    # Тест оптимизированного сопоставления
    start = time.time()
    result = asyncio.run(async_match_positions(test_positions, products))
    opt_time = time.time() - start
    print(f'Optimized matching: {opt_time:.4f}s')
    
    # Сравнение
    if opt_time < std_time:
        improvement = (1 - opt_time/std_time) * 100
        print(f'Optimization improved performance by {improvement:.1f}%')
    else:
        print('No performance improvement detected')
    
    return True

try:
    test_matching()
except Exception as e:
    print(f'Error testing matching: {e}')
    sys.exit(1)
" > "$TEST_DIR/matching_test.txt" 2>&1
    
    echo "Matching test completed, results in $TEST_DIR/matching_test.txt"
    echo ""
}

# Запуск всех тестов
echo "Starting tests..."
echo "Results will be saved to $TEST_DIR directory"
echo ""

test_startup_time
test_redis_cache
test_matching

echo "All tests completed!"
echo "Check $TEST_DIR for detailed results"
