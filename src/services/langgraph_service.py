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
                try:
                    assistant = self.sdk.assistants.get(assistant_id)
                    return assistant
                except Exception as e:
                    return None
            
            return None
        except Exception as e:
            return None
    
    def get_or_create_assistant(self, instruction: str, tools: list = None, name: str = None):
        """Получить существующего Assistant по имени или создать нового
        Проверяет, совпадают ли инструменты, и пересоздает Assistant если нужно
        
        Args:
            instruction: Инструкция для ассистента
            tools: Список инструментов (уже созданные через sdk.tools.function)
            name: Имя ассистента
        """
        # Если имя указано, пытаемся найти существующего
        if name:
            existing = self.find_assistant_by_name(name)
            if existing:
                # Получаем имена существующих инструментов
                existing_tools = getattr(existing, 'tools', None) or []
                existing_tool_names = set()
                for tool in existing_tools:
                    if hasattr(tool, 'function'):
                        func = tool.function
                        if hasattr(func, 'name'):
                            existing_tool_names.add(func.name)
                        elif isinstance(func, dict) and 'name' in func:
                            existing_tool_names.add(func['name'])
                
                # Получаем имена новых инструментов
                new_tool_names = set()
                if tools:
                    for tool in tools:
                        if hasattr(tool, 'function'):
                            func = tool.function
                            if hasattr(func, 'name'):
                                new_tool_names.add(func.name)
                            elif isinstance(func, dict) and 'name' in func:
                                new_tool_names.add(func['name'])
                
                # Если инструменты не совпадают, пересоздаем Assistant
                if existing_tool_names != new_tool_names:
                    logger.info(f"Инструменты Assistant '{name}' не совпадают. Пересоздаём Assistant.")
                    logger.debug(f"Существующие инструменты: {existing_tool_names}")
                    logger.debug(f"Новые инструменты: {new_tool_names}")
                    try:
                        existing.delete()
                        logger.info(f"Старый Assistant '{name}' удалён")
                    except Exception as e:
                        logger.warning(f"Не удалось удалить старый Assistant: {e}")
                    # Создаём новый с правильными инструментами
                    return self.create_assistant(instruction=instruction, tools=tools, name=name, skip_ydb_save=False)
                else:
                    # Инструменты совпадают, обновляем только инструкцию если нужно
                    if instruction:
                        try:
                            existing.update(instruction=instruction)
                        except Exception as e:
                            logger.warning(f"Не удалось обновить инструкцию Assistant: {e}")
                    return existing
        
        # Если не нашли или имя не указано - создаём нового без сохранения в YDB (для Playground)
        return self.create_assistant(instruction=instruction, tools=tools, name=name, skip_ydb_save=True)
    
    def create_assistant(self, instruction: str, tools: list = None, name: str = None, skip_ydb_save: bool = False):
        """Создание Assistant с инструкцией и инструментами
        
        Args:
            instruction: Инструкция для ассистента
            tools: Список инструментов (уже созданные через sdk.tools.function)
            name: Имя ассистента
            skip_ydb_save: Если True, не сохраняет ID в YDB (для Playground)
        """
        kwargs = {}
        if tools and len(tools) > 0:
            kwargs = {"tools": tools}
            # Логируем, что реально передается в SDK
            logger.debug(f"Создание Assistant с {len(tools)} инструментами")
            for i, tool in enumerate(tools):
                if hasattr(tool, 'function'):
                    func = tool.function
                    tool_name = getattr(func, 'name', 'UNKNOWN')
                    tool_desc_len = len(getattr(func, 'description', ''))
                    params = getattr(func, 'parameters', None)
                    if isinstance(params, dict):
                        params_size = len(str(params))
                    else:
                        params_size = len(str(params)) if params else 0
                    logger.debug(f"  Tool {i+1}: {tool_name}, description: {tool_desc_len} символов, parameters: {params_size} символов")
        
        # Добавляем имя если указано
        if name:
            kwargs["name"] = name
        
        try:
            assistant = self.sdk.assistants.create(
                self.model,
                ttl_days=30,
                expiration_policy="since_last_active",
                temperature=0.1,
                max_tokens=6000,
                **kwargs
            )
        except Exception as e:
            logger.error(f"❌ Ошибка создания Assistant в Yandex Cloud: {e}", exc_info=True)
            raise
        
        if instruction:
            try:
                assistant.update(instruction=instruction)
            except Exception as e:
                logger.error(f"❌ Ошибка обновления инструкции: {e}", exc_info=True)
                raise
        
        # Сохраняем ID в YDB для переиспользования (если не пропущено)
        if not skip_ydb_save and name and assistant.id:
            try:
                ydb_client = get_ydb_client()
                ydb_client.save_assistant_id(name, assistant.id)
            except Exception as e:
                logger.error(f"❌ Не удалось сохранить ID ассистента в YDB: {e}", exc_info=True)
        
        return assistant

