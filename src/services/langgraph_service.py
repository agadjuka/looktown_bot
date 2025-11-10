"""
Сервис для работы с LangGraph и Assistant API
"""
import os
from typing import Optional
from yandex_cloud_ml_sdk import YCloudML
from yandex_cloud_ml_sdk._threads.thread import Thread
from ..ydb_client import get_ydb_client
from .logger_service import logger


class LangGraphService:
    """Сервис для работы с LangGraph и Assistant API"""
    
    def __init__(self):
        folder_id = os.getenv("YANDEX_FOLDER_ID")
        api_key = os.getenv("YANDEX_API_KEY_SECRET")
        
        if not folder_id or not api_key:
            raise ValueError("Не заданы YANDEX_FOLDER_ID или YANDEX_API_KEY_SECRET")
        
        self.sdk = YCloudML(folder_id=folder_id, auth=api_key)
        self.model = self.sdk.models.completions("gpt://b1g7c2htkq0v3rfat0ra/gpt-oss-120b/latest")
    
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
    
    def find_assistant_by_name(self, name: str):
        """Поиск существующего Assistant по имени через YDB
        
        Args:
            name: Имя ассистента
        """
        try:
            ydb_client = get_ydb_client()
            assistant_id = ydb_client.get_assistant_id(name)
            
            if assistant_id:
                logger.info(f"Найден ID ассистента '{name}' в YDB: {assistant_id}")
                try:
                    assistant = self.sdk.assistants.get(assistant_id)
                    logger.info(f"Успешно загружен ассистент '{name}' по ID: {assistant_id}")
                    return assistant
                except Exception as e:
                    # Просто возвращаем None, не удаляя из YDB
                    logger.info(f"Ассистент с ID {assistant_id} не найден в Yandex Cloud: {e}")
                    return None
            
            logger.info(f"Ассистент '{name}' не найден в YDB")
            return None
        except Exception as e:
            logger.warning(f"Ошибка при поиске ассистента по имени: {e}")
            return None
    
    def get_or_create_assistant(self, instruction: str, tools: list = None, name: str = None):
        """Получить существующего Assistant по имени или создать нового
        
        Args:
            instruction: Инструкция для ассистента
            tools: Список инструментов
            name: Имя ассистента
        """
        # Если имя указано, пытаемся найти существующего
        if name:
            existing = self.find_assistant_by_name(name)
            if existing:
                logger.info(f"Используем существующего ассистента: {name}")
                return existing
        
        # Если не нашли или имя не указано - создаём нового без сохранения в YDB (для Playground)
        return self.create_assistant(instruction=instruction, tools=tools, name=name, skip_ydb_save=True)
    
    def create_assistant(self, instruction: str, tools: list = None, name: str = None, skip_ydb_save: bool = False):
        """Создание Assistant с инструкцией и инструментами
        
        Args:
            instruction: Инструкция для ассистента
            tools: Список инструментов
            name: Имя ассистента
            skip_ydb_save: Если True, не сохраняет ID в YDB (для Playground)
        """
        logger.info(f"=== СОЗДАНИЕ ASSISTANT ===")
        logger.info(f"name: {name}")
        logger.info(f"instruction длина: {len(instruction) if instruction else 0}")
        logger.info(f"tools: {len(tools) if tools else 0}")
        
        kwargs = {}
        if tools and len(tools) > 0:
            kwargs = {"tools": tools}
            logger.info(f"Инструменты добавлены в kwargs")
        
        # Добавляем имя если указано
        if name:
            kwargs["name"] = name
            logger.info(f"Имя добавлено в kwargs: {name}")
        
        logger.info(f"Создание нового ассистента: {name or 'Без имени'}")
        try:
            assistant = self.sdk.assistants.create(
                self.model,
                ttl_days=30,
                expiration_policy="since_last_active",
                temperature=0.1,
                max_tokens=6000,
                **kwargs
            )
            logger.info(f"✅ Assistant создан в Yandex Cloud: ID={assistant.id}")
        except Exception as e:
            logger.error(f"❌ Ошибка создания Assistant в Yandex Cloud: {e}", exc_info=True)
            raise
        
        if instruction:
            try:
                logger.info("Обновление инструкции...")
                assistant.update(instruction=instruction)
                logger.info("✅ Инструкция обновлена")
            except Exception as e:
                logger.error(f"❌ Ошибка обновления инструкции: {e}", exc_info=True)
                raise
        
        # Сохраняем ID в YDB для переиспользования (если не пропущено)
        if not skip_ydb_save and name and assistant.id:
            try:
                logger.info(f"Сохранение ID в YDB: name={name}, id={assistant.id}")
                ydb_client = get_ydb_client()
                ydb_client.save_assistant_id(name, assistant.id)
                logger.info(f"✅ ID ассистента '{name}' сохранён в YDB: {assistant.id}")
                
                # Проверяем, что действительно сохранилось
                saved_id = ydb_client.get_assistant_id(name)
                if saved_id == assistant.id:
                    logger.info(f"✅ Проверка: ID корректно сохранён в YDB")
                else:
                    logger.error(f"❌ Проверка не прошла! Ожидалось: {assistant.id}, получено: {saved_id}")
            except Exception as e:
                logger.error(f"❌ Не удалось сохранить ID ассистента в YDB: {e}", exc_info=True)
                # Не прерываем выполнение, но логируем ошибку
        elif skip_ydb_save:
            logger.info(f"⏭️ Пропущено сохранение в YDB (skip_ydb_save=True)")
        else:
            logger.warning(f"⚠️ Не сохранено в YDB: name={name}, assistant.id={assistant.id if assistant else None}")
        
        return assistant

