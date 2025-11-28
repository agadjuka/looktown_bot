"""Скрипт для создания таблицы adminpanel в YDB"""
import sys
import os

# Загружаем переменные окружения из .env файла
from dotenv import load_dotenv
load_dotenv()

# Добавляем путь к src для импорта модулей
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.ydb_client import YDBClient


def main():
    """Создание таблицы adminpanel в базе данных YDB"""
    try:
        print("🔌 Подключение к YDB...")
        client = YDBClient()
        
        print("📊 Создание таблицы adminpanel...")
        client.create_adminpanel_table()
        
        print("✅ Таблица adminpanel успешно создана!")
        print("\nСтруктура таблицы:")
        print("  - user_id (String) - ID пользователя")
        print("  - topic_id (String) - ID топика")
        print("  - topic_name (String) - Название топика")
        print("  - PRIMARY KEY (user_id, topic_id)")
        
        client.close()
        
    except ValueError as e:
        print(f"❌ Ошибка конфигурации: {e}")
        print("\nУбедитесь, что в переменных окружения заданы:")
        print("  - YDB_ENDPOINT")
        print("  - YDB_DATABASE")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка при создании таблицы: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

