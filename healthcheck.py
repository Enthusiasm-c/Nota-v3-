import redis
import sys
import psycopg2
import openai
from app.config import settings

def check_redis_health():
    try:
        r = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)
        r.ping()
        print("[OK] Redis доступен")
        return True
    except Exception as e:
        print(f"[FAIL] Redis не отвечает: {e}")
        return False

def check_postgres_health():
    try:
        # Пример: PG_DSN должен быть в env или settings
        dsn = getattr(settings, "POSTGRES_DSN", None) or \
              getattr(settings, "DATABASE_URL", None) or \
              "dbname=nota user=nota password=nota host=localhost port=5432"
        conn = psycopg2.connect(dsn, connect_timeout=3)
        conn.close()
        print("[OK] PostgreSQL доступен")
        return True
    except Exception as e:
        print(f"[FAIL] PostgreSQL не отвечает: {e}")
        return False

def check_openai_health():
    try:
        openai.api_key = settings.OPENAI_API_KEY
        # Пробуем получить список моделей (быстро и без затрат)
        openai.Model.list()
        print("[OK] OpenAI API доступен")
        return True
    except Exception as e:
        print(f"[FAIL] OpenAI API не отвечает: {e}")
        return False

def main():
    failed = False
    if not check_redis_health():
        failed = True
    if not check_postgres_health():
        failed = True
    if not check_openai_health():
        failed = True
    if failed:
        sys.exit(1)
    print("[OK] Все сервисы работают")

if __name__ == "__main__":
    main()
