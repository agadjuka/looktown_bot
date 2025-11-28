"""Скрипт для добавления колонки mode в таблицу adminpanel в YDB"""
import sys
import os

# Загружаем переменные окружения из .env файла
from dotenv import load_dotenv
load_dotenv()

# Добавляем путь к src для импорта модулей
sys.path.insert(0, os.path.dirname(__file__))

from src.ydb_client import YDBClient


def main():
    """Добавление колонки mode в таблицу adminpanel"""
    try:
        print("🔌 Подключение к YDB...")
        client = YDBClient()
        
        print("📊 Добавление колонки mode в таблицу adminpanel...")
        
        # В YDB для добавления колонки используется ALTER TABLE
        alter_table_query = """
        ALTER TABLE adminpanel ADD COLUMN mode String;
        """
        
        def _tx(session):
            return session.execute_scheme(alter_table_query)
        
        client.pool.retry_operation_sync(_tx)
        
        print("✅ Колонка mode успешно добавлена в таблицу adminpanel!")
        print("\nСтруктура таблицы теперь:")
        print("  - user_id (String) - ID пользователя (PRIMARY KEY)")
        print("  - topic_id (String) - ID топика")
        print("  - topic_name (String) - Название топика")
        print("  - mode (String) - Режим работы (auto/manual)")
        
        client.close()
        
    except ValueError as e:
        print(f"❌ Ошибка конфигурации: {e}")
        print("\nУбедитесь, что в переменных окружения заданы:")
        print("  - YDB_ENDPOINT")
        print("  - YDB_DATABASE")
        sys.exit(1)
    except Exception as e:
        # Проверяем, не добавлена ли уже колонка
        error_msg = str(e).lower()
        if "already exists" in error_msg or "уже существует" in error_msg:
            print("ℹ️ Колонка mode уже существует в таблице adminpanel")
            print("✅ Никаких изменений не требуется")
        else:
            print(f"❌ Ошибка при добавлении колонки: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()

