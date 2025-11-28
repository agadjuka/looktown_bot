"""
Модуль для работы с LangGraph (Responses API)
"""
import os
import time
import asyncio
from datetime import datetime
import pytz
from typing import Optional, List, Dict, Any
from ..ydb_client import get_ydb_client
from .auth_service import AuthService
from .debug_service import DebugService
from .logger_service import logger
from ..graph.main_graph import MainGraph
from .langgraph_service import LangGraphService
import requests


class YandexAgentService:
    """Сервис для работы с LangGraph (Responses API)"""
    
    def __init__(self, auth_service: AuthService, debug_service: DebugService):
        """Инициализация сервиса с внедрением зависимостей"""
        self.auth_service = auth_service
        self.debug_service = debug_service
        
        # Инициализация YDB клиента
        self.ydb_client = get_ydb_client()
        
        # Ленивая инициализация LangGraph
        self._langgraph_service = None
        self._main_graph = None
        
        # Инициализация кэша времени
        self._time_cache = None
        self._time_cache_timestamp = 0
    
    @property
    def langgraph_service(self) -> LangGraphService:
        """Ленивая инициализация LangGraphService"""
        if self._langgraph_service is None:
            self._langgraph_service = LangGraphService()
        return self._langgraph_service
    
    @property
    def main_graph(self) -> MainGraph:
        """Ленивая инициализация MainGraph"""
        if self._main_graph is None:
            self._main_graph = MainGraph(self.langgraph_service)
        return self._main_graph
    
    def _get_moscow_time(self) -> str:
        """Получить текущее время и дату в московском часовом поясе через внешний API"""
        current_time = time.time()
        
        # Используем кэш, если прошло меньше минуты
        if self._time_cache and (current_time - self._time_cache_timestamp) < 60:
            return self._time_cache
        
        try:
            # Получаем точное время через WorldTimeAPI
            response = requests.get(
                'http://worldtimeapi.org/api/timezone/Europe/Moscow',
                timeout=2
            )
            response.raise_for_status()
            data = response.json()
            datetime_str = data['datetime']
            
            # Преобразуем строку в datetime
            if datetime_str.endswith('Z'):
                datetime_str = datetime_str[:-1] + '+00:00'
            moscow_time = datetime.fromisoformat(datetime_str)
            
            # Форматируем
            date_time_str = moscow_time.strftime("%Y-%m-%d %H:%M")
            result = f"Текущее время: {date_time_str}"
            
            # Сохраняем в кэш
            self._time_cache = result
            self._time_cache_timestamp = current_time
            
            return result
        except Exception:
            # Fallback на системное время
            moscow_tz = pytz.timezone('Europe/Moscow')
            moscow_time = datetime.now(moscow_tz)
            date_time_str = moscow_time.strftime("%Y-%m-%d %H:%M")
            result = f"Текущее время: {date_time_str}"
            
            # Кэшируем fallback тоже
            self._time_cache = result
            self._time_cache_timestamp = current_time
            
            return result
    
    async def send_to_agent_langgraph(self, chat_id: str, user_text: str) -> dict:
        """Отправка сообщения через LangGraph (Responses API)"""
        from ..graph.conversation_state import ConversationState
        
        # Получаем last_response_id для продолжения диалога
        last_response_id = await asyncio.to_thread(
            self.ydb_client.get_last_response_id,
            chat_id
        )
        
        # Добавляем московское время в начало сообщения
        moscow_time = self._get_moscow_time()
        input_with_time = f"[{moscow_time}] {user_text}"
        
        # Создаём начальное состояние
        initial_state: ConversationState = {
            "message": input_with_time,
            "previous_response_id": last_response_id,
            "chat_id": chat_id,
            "stage": None,
            "extracted_info": None,
            "answer": "",
            "manager_alert": None
        }
        
        # Выполняем граф
        result_state = await asyncio.to_thread(
            self.main_graph.compiled_graph.invoke,
            initial_state
        )
        
        # Сохраняем response_id для следующего запроса
        response_id = result_state.get("response_id")
        if response_id:
            await asyncio.to_thread(
                self.ydb_client.save_response_id,
                chat_id,
                response_id
            )
        
        # Извлекаем ответ
        answer = result_state.get("answer", "")
        manager_alert = result_state.get("manager_alert")
        
        # Нормализуем даты и время в ответе
        from .date_normalizer import normalize_dates_in_text
        from .time_normalizer import normalize_times_in_text
        from .link_converter import convert_yclients_links_in_text
        
        answer = normalize_dates_in_text(answer)
        answer = normalize_times_in_text(answer)
        answer = convert_yclients_links_in_text(answer)
        
        result = {"user_message": answer}
        if manager_alert:
            manager_alert = normalize_dates_in_text(manager_alert)
            manager_alert = normalize_times_in_text(manager_alert)
            manager_alert = convert_yclients_links_in_text(manager_alert)
            result["manager_alert"] = manager_alert
        
        return result
    
    async def send_to_agent(self, chat_id: str, user_text: str) -> dict:
        """Отправка сообщения агенту через LangGraph"""
        return await self.send_to_agent_langgraph(chat_id, user_text)
    
    async def reset_context(self, chat_id: str):
        """Сброс контекста для чата"""
        try:
            # Сбрасываем last_response_id
            await asyncio.to_thread(
                self.ydb_client.reset_context,
                chat_id
            )
            
            # Очищаем историю результатов инструментов
            try:
                from .tool_history_service import get_tool_history_service
                tool_history_service = get_tool_history_service()
                tool_history_service.clear_history(chat_id)
                logger.debug(f"История результатов инструментов очищена для chat_id={chat_id}")
            except Exception as e:
                logger.debug(f"Ошибка при очистке истории результатов инструментов: {e}")
            
            logger.ydb("Контекст сброшен", chat_id)
        except Exception as e:
            logger.error("Ошибка при сбросе контекста", str(e))
