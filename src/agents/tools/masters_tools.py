"""
Инструмент для получения информации о мастерах
"""
import json
from pydantic import BaseModel
from yandex_cloud_ml_sdk._threads.thread import Thread

# Импорты
from .masters_data_loader import _masters_data_loader

try:
    from ..services.logger_service import logger
except ImportError:
    # Простой logger для случаев, когда logger_service недоступен
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class Masters(BaseModel):
    """
    Получить полную информацию о мастерах салона.
    Используй когда клиент спрашивает "какие у вас мастера?", "расскажите про мастеров", "кто работает в салоне" или подобные вопросы о мастерах.
    """
    
    def process(self, thread: Thread) -> str:
        """
        Получение информации о мастерах
        
        Returns:
            Полное содержимое файла masters.json в читаемом формате
        """
        try:
            data = _masters_data_loader.load_data()
            
            if not data:
                return "Информация о мастерах не найдена"
            
            # Возвращаем полное содержимое JSON в читаемом формате
            return json.dumps(data, ensure_ascii=False, indent=2)
            
        except FileNotFoundError as e:
            logger.error(f"Файл с информацией о мастерах не найден: {e}")
            return "Файл с информацией о мастерах не найден"
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            return "Ошибка при чтении информации о мастерах"
        except Exception as e:
            logger.error(f"Ошибка при получении информации о мастерах: {e}")
            return f"Ошибка при получении информации о мастерах: {str(e)}"














