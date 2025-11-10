"""
Сервис для работы с LangGraph и Assistant API
"""
import os
from typing import Optional
from yandex_cloud_ml_sdk import YCloudML
from yandex_cloud_ml_sdk._threads.thread import Thread
from .logger_service import logger


class LangGraphService:
    """Сервис для работы с LangGraph и Assistant API"""
    
    def __init__(self):
        folder_id = os.getenv("YANDEX_FOLDER_ID")
        api_key = os.getenv("YANDEX_API_KEY_SECRET")
        
        if not folder_id or not api_key:
            raise ValueError("Не заданы YANDEX_FOLDER_ID или YANDEX_API_KEY_SECRET")
        
        self.sdk = YCloudML(folder_id=folder_id, auth=api_key)
        self.model = self.sdk.models.completions("yandexgpt", model_version="rc")
    
    def create_thread(self, ttl_days: int = 30) -> Thread:
        """Создание нового Thread"""
        return self.sdk.threads.create(
            ttl_days=ttl_days,
            expiration_policy="since_last_active"
        )
    
    def get_thread_by_id(self, thread_id: str) -> Optional[Thread]:
        """Получение Thread по ID"""
        try:
            return self.sdk.threads.get(thread_id)
        except Exception as e:
            logger.error(f"Ошибка получения Thread: {e}")
            return None
    
    def create_assistant(self, instruction: str, tools: list = None):
        """Создание Assistant с инструкцией и инструментами"""
        kwargs = {}
        if tools and len(tools) > 0:
            kwargs = {"tools": tools}
        
        assistant = self.sdk.assistants.create(
            self.model,
            ttl_days=30,
            expiration_policy="since_last_active",
            **kwargs
        )
        
        if instruction:
            assistant.update(instruction=instruction)
        
        return assistant

