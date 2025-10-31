"""
Сервис для отладки и логирования запросов
"""
import json
from datetime import datetime
from .logger_service import logger


class DebugService:
    """Сервис для сохранения debug-логов"""
    
    def __init__(self):
        """Инициализация сервиса отладки"""
        pass
    
    def save_request(self, payload: dict, chat_id: str):
        """Сохранить запрос к LLM в файл для дебага"""
        try:
            # Создаем имя файла с временной меткой
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"debug_logs/llm_request_{chat_id}_{timestamp}.json"
            
            # Сохраняем payload как есть, без форматирования
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=None, separators=(',', ':'))
            
            logger.debug("Запрос к LLM сохранен", filename)
            
        except Exception as e:
            logger.error("Ошибка при сохранении запроса", str(e))
    
    def save_response(self, response: dict, chat_id: str):
        """Сохранить ответ от LLM в файл для дебага"""
        try:
            # Создаем имя файла с временной меткой
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"debug_logs/llm_response_{chat_id}_{timestamp}.json"
            
            # Сохраняем response как есть, без форматирования
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(response, f, ensure_ascii=False, indent=None, separators=(',', ':'))
            
            logger.debug("Ответ от LLM сохранен", filename)
            
        except Exception as e:
            logger.error("Ошибка при сохранении ответа", str(e))