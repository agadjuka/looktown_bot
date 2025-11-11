"""
Модуль для работы с LangGraph (основной метод) и Responses API (fallback)
"""
import os
import time
import random
import requests
import asyncio
from datetime import datetime
import pytz
from typing import Optional
from ..ydb_client import get_ydb_client
from .auth_service import AuthService
from .debug_service import DebugService
from .escalation_service import EscalationService
from .logger_service import logger
from ..graph.booking_graph import BookingGraph
from .langgraph_service import LangGraphService


class YandexAgentService:
    """Сервис для работы с LangGraph (основной метод) и Responses API (fallback)"""
    
    def __init__(self, auth_service: AuthService, debug_service: DebugService, escalation_service: EscalationService):
        """Инициализация сервиса с внедрением зависимостей"""
        self.auth_service = auth_service
        self.debug_service = debug_service
        self.escalation_service = escalation_service
        
        # Используем существующие переменные из вашего .env файла
        self.base_url = os.getenv("RESPONSES_BASE_URL", "https://rest-assistant.api.cloud.yandex.net/v1")
        self.prompt_id = os.getenv("PROMPT_ID")
        self.agent_id = os.getenv("YC_AGENT_ID")  # Используем существующий YC_AGENT_ID
        
        if not self.prompt_id and not self.agent_id:
            raise ValueError("Не задан ни PROMPT_ID, ни YC_AGENT_ID в переменных окружения")
        
        # Инициализация YDB клиента
        self.ydb_client = get_ydb_client()
        
        # Ленивая инициализация LangGraph
        self._langgraph_service = None
        self._booking_graph = None
        
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
    def booking_graph(self) -> BookingGraph:
        """Ленивая инициализация BookingGraph"""
        if self._booking_graph is None:
            self._booking_graph = BookingGraph(self.langgraph_service)
        return self._booking_graph
    
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
            
            # Преобразуем строку в datetime (формат: 2024-10-27T13:31:06.123456+03:00)
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
            # Fallback на системное время, если API недоступен
            moscow_tz = pytz.timezone('Europe/Moscow')
            moscow_time = datetime.now(moscow_tz)
            date_time_str = moscow_time.strftime("%Y-%m-%d %H:%M")
            result = f"Текущее время: {date_time_str}"
            
            # Кэшируем fallback тоже
            self._time_cache = result
            self._time_cache_timestamp = current_time
            
            return result
    
    async def _retry_with_backoff(self, coro_func, max_retries=3):
        """Ретраи с экспоненциальным backoff для async функций (не блокирует event loop)"""
        for attempt in range(max_retries):
            try:
                # Создаем новую корутину при каждой попытке
                coro = coro_func()
                return await coro
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                
                # Экспоненциальный backoff с джиттером (неблокирующий)
                delay = (2 ** attempt) + random.uniform(0, 1)
                await asyncio.sleep(delay)
    
    def _is_internal_server_error(self, error_message: str) -> bool:
        """
        Проверяет, является ли ошибка одной из ошибок, требующих повторной попытки:
        - "Internal server error"
        - "Empty response from API"
        
        :param error_message: Текст ошибки
        :return: True, если это ошибка, требующая повторной попытки
        """
        error_lower = error_message.lower()
        return "internal server error" in error_lower or "empty response from api" in error_lower

    async def _make_api_request(self, payload: dict) -> dict:
        """Выполнение запроса к Responses API (асинхронный, не блокирует event loop)"""
        # Пытаемся использовать IAM токен (для инструментов)
        # Если сервисный аккаунт не настроен, сразу используем API ключ
        if self.auth_service.is_service_account_configured():
            try:
                # Получаем IAM токен асинхронно через executor (так как метод синхронный)
                loop = asyncio.get_event_loop()
                iam_token = await loop.run_in_executor(
                    None,
                    self.auth_service.get_iam_token
                )
                headers = {
                    "Authorization": f"Bearer {iam_token}",
                    "Content-Type": "application/json"
                }
                logger.debug("Используем Bearer токен (IAM)")
            except Exception as e:
                logger.debug("Fallback к API ключу", str(e))
                # Fallback к API ключу при ошибке получения IAM токена
                headers = {
                    "Authorization": f"Api-Key {self.auth_service.get_api_key()}",
                    "x-folder-id": os.getenv("YANDEX_FOLDER_ID"),
                    "Content-Type": "application/json"
                }
        else:
            # Используем API ключ, если сервисный аккаунт не настроен
            # В Yandex Cloud Serverless Containers это нормальная ситуация
            logger.debug("Используем API ключ (сервисный аккаунт не настроен)")
            headers = {
                "Authorization": f"Api-Key {self.auth_service.get_api_key()}",
                "x-folder-id": os.getenv("YANDEX_FOLDER_ID"),
                "Content-Type": "application/json"
            }
        
        # Полный URL с путем /responses
        full_url = f"{self.base_url}/responses"
        
        # КРИТИЧЕСКИ ВАЖНО: Обертываем синхронный requests.post() в executor,
        # чтобы не блокировать event loop во время ожидания ответа от нейронки
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,  # Используем default executor (ThreadPoolExecutor)
            lambda: requests.post(
                full_url,
                headers=headers,
                json=payload,
                timeout=30
            )
        )
        
        if response.status_code != 200:
            raise Exception(f"API request failed with status {response.status_code}: {response.text}")
        
        return response.json()
    
    async def _retry_internal_server_error(self, chat_id: str, user_text: str, first_error_message: str) -> dict:
        """
        Выполняет повторную попытку при ошибке Internal server error или Empty response from API.
        Если повторная попытка тоже возвращает ошибку, отправляет менеджер-алерт.
        
        :param chat_id: ID чата
        :param user_text: Исходное сообщение пользователя
        :param first_error_message: Сообщение об ошибке из первой попытки
        :return: Словарь с ответом для пользователя и менеджер-алертом (если нужно)
        """
        try:
            logger.info(f"Выполняем повторную попытку при ошибке: {first_error_message}", chat_id)
            
            # Получаем last_response_id из YDB
            previous_response_id = await asyncio.to_thread(
                self.ydb_client.get_last_response_id,
                chat_id
            )
            
            # Добавляем московское время в начало сообщения
            moscow_time = self._get_moscow_time()
            input_with_time = f"[{moscow_time}] {user_text}"
            
            # Формируем payload для повторного запроса (точно такой же, как первый)
            payload = {
                "prompt": {
                    "id": self.agent_id,
                    "variables": {}
                },
                "input": input_with_time,
                "chat_options": {
                    "chat_id": chat_id
                },
                "tool_choice": "auto",
                "service_account_id": os.getenv("YANDEX_SERVICE_ACCOUNT_ID", "")
            }
            
            # Добавляем previous_response_id если есть
            if previous_response_id:
                payload["previous_response_id"] = previous_response_id
            
            # Выполняем повторный запрос
            result = await self._make_api_request(payload)
            
            # Сохраняем ответ для дебага
            await asyncio.to_thread(
                self.debug_service.save_response,
                result,
                f"{chat_id}_retry_ise"
            )
            
            # Проверяем статус ответа
            status = result.get("status", "")
            if status == "failed":
                error_info = result.get("error", {})
                error_message = error_info.get("message", "Неизвестная ошибка")
                
                # Если повторная попытка тоже вернула Internal server error или Empty response, отправляем менеджер-алерт
                if self._is_internal_server_error(error_message):
                    logger.error("Повторная попытка тоже вернула ошибку, отправляем менеджер-алерт", chat_id)
                    return self.escalation_service.handle_api_error(
                        error_message,
                        chat_id,
                        user_text
                    )
                else:
                    # Если другая ошибка, возвращаем её
                    return {"user_message": f"⚠️ Ошибка API: {error_message}"}
            
            # Если запрос успешен, обрабатываем ответ как обычно
            response_id = result.get("id")
            response_text = ""
            
            # Извлекаем текст ответа
            if "output" in result and isinstance(result["output"], list) and len(result["output"]) > 0:
                for output_item in reversed(result["output"]):
                    if output_item.get("type") == "message" and "content" in output_item:
                        content = output_item["content"]
                        if content and len(content) > 0:
                            text_content = content[0].get("text", "")
                            if not text_content.strip().startswith("{") and not "stage" in text_content:
                                response_text = text_content
                                break
            
            if not response_text:
                if "error" in result and result["error"]:
                    error_info = result["error"]
                    error_message = error_info.get("message", "Неизвестная ошибка")
                    # Если повторная попытка тоже вернула Internal server error или Empty response, отправляем менеджер-алерт
                    if self._is_internal_server_error(error_message):
                        logger.error("Повторная попытка тоже вернула ошибку, отправляем менеджер-алерт", chat_id)
                        return self.escalation_service.handle_api_error(
                            error_message,
                            chat_id,
                            user_text
                        )
                    return {"user_message": f"⚠️ Ошибка: {error_message}"}
                else:
                    # Если повторная попытка тоже вернула Empty response from API, отправляем менеджер-алерт
                    error_message = "Empty response from API"
                    logger.error("Повторная попытка тоже вернула Empty response from API, отправляем менеджер-алерт", chat_id)
                    return self.escalation_service.handle_api_error(
                        error_message,
                        chat_id,
                        user_text
                    )
            
            # Сохраняем response_id
            if response_id:
                await asyncio.to_thread(
                    self.ydb_client.save_response_id,
                    chat_id,
                    response_id
                )
                logger.ydb("Сохранен response_id (retry)", chat_id)
            
            logger.success("Повторная попытка выполнена успешно", chat_id)
            
            # Проверяем на эскалацию
            final_text = response_text
            if final_text.strip().startswith('[CALL_MANAGER]'):
                return self.escalation_service.handle(final_text, chat_id)
            return {"user_message": final_text}
            
        except Exception as retry_error:
            error_msg = str(retry_error)
            logger.error("Ошибка при повторной попытке", error_msg)
            
            # Если повторная попытка тоже вернула Internal server error или Empty response, отправляем менеджер-алерт
            if self._is_internal_server_error(error_msg):
                logger.error("Повторная попытка тоже вернула ошибку в исключении, отправляем менеджер-алерт", chat_id)
                return self.escalation_service.handle_api_error(
                    error_msg,
                    chat_id,
                    user_text
                )
            
            # Если другая ошибка, возвращаем её
            return {"user_message": f"Ошибка при повторном запросе: {error_msg}"}
    
    async def send_to_agent_langgraph(self, chat_id: str, user_text: str) -> dict:
        """Отправка сообщения через LangGraph (основной метод обработки)"""
        from ..graph.booking_state import BookingState
        
        # Получаем или создаём Thread
        thread_id = await asyncio.to_thread(
            self.ydb_client.get_thread_id,
            chat_id
        )
        
        if thread_id:
            thread = self.langgraph_service.get_thread_by_id(thread_id)
            if not thread:
                # Thread не найден, создаём новый
                thread = self.langgraph_service.create_thread()
                await asyncio.to_thread(
                    self.ydb_client.save_thread_id,
                    chat_id,
                    thread.id
                )
        else:
            # Создаём новый Thread
            thread = self.langgraph_service.create_thread()
            await asyncio.to_thread(
                self.ydb_client.save_thread_id,
                chat_id,
                thread.id
            )
        
        # Добавляем московское время в начало сообщения (как в первом боте)
        moscow_time = self._get_moscow_time()
        input_with_time = f"[{moscow_time}] {user_text}"
        
        # Создаём начальное состояние
        initial_state: BookingState = {
            "message": input_with_time,
            "thread": thread,
            "stage": None,
            "extracted_info": None,
            "answer": "",
            "manager_alert": None
        }
        
        # Выполняем граф
        result_state = await asyncio.to_thread(
            self.booking_graph.invoke,
            initial_state
        )
        
        # Извлекаем ответ
        answer = result_state.get("answer", "")
        manager_alert = result_state.get("manager_alert")
        
        # Нормализуем даты и время в ответе (как в первом боте)
        from .date_normalizer import normalize_dates_in_text
        from .time_normalizer import normalize_times_in_text
        
        answer = normalize_dates_in_text(answer)
        answer = normalize_times_in_text(answer)
        
        # Проверяем на эскалацию
        if answer.strip().startswith('[CALL_MANAGER]'):
            return self.escalation_service.handle(answer, chat_id)
        
        result = {"user_message": answer}
        if manager_alert:
            manager_alert = normalize_dates_in_text(manager_alert)
            manager_alert = normalize_times_in_text(manager_alert)
            result["manager_alert"] = manager_alert
        
        return result
    
    async def _send_to_agent_responses_api(self, chat_id: str, user_text: str) -> dict:
        """Отправка сообщения агенту через Responses API с памятью (асинхронный, не блокирует event loop)"""
        try:
            start_time = time.time()
            
            # Получаем last_response_id из YDB через executor (не блокирует event loop)
            previous_response_id = await asyncio.to_thread(
                self.ydb_client.get_last_response_id,
                chat_id
            )
            
            logger.debug("Получен previous_response_id", f"chat_id={chat_id}")
            
            # Добавляем московское время в начало сообщения
            moscow_time = self._get_moscow_time()
            input_with_time = f"[{moscow_time}] {user_text}"
            
            # Формируем payload для Responses API
            payload = {
                "prompt": {
                    "id": self.agent_id,
                    "variables": {}
                },
                "input": input_with_time,
                "chat_options": {
                    "chat_id": chat_id
                },
                "tool_choice": "auto",
                "service_account_id": os.getenv("YANDEX_SERVICE_ACCOUNT_ID", "")  # Используем вашу переменную
            }
            
            # Добавляем previous_response_id если есть
            if previous_response_id:
                payload["previous_response_id"] = previous_response_id
            
            # Сохраняем запрос для дебага через executor (быстрая операция, но для консистентности)
            await asyncio.to_thread(
                self.debug_service.save_request,
                payload,
                chat_id
            )
            
            # Выполняем запрос с ретраями (асинхронно, не блокирует event loop)
            result = await self._retry_with_backoff(
                lambda: self._make_api_request(payload)
            )
            
            # Сохраняем ответ от LLM для дебага через executor
            await asyncio.to_thread(
                self.debug_service.save_response,
                result,
                chat_id
            )
            
            # Извлекаем response_id и текст ответа
            response_id = result.get("id")
            response_text = ""
            
            # Проверяем статус ответа
            status = result.get("status", "")
            if status == "failed":
                error_info = result.get("error", {})
                error_message = error_info.get("message", "Неизвестная ошибка")
                error_code = error_info.get("code", "")
                
                # Если ошибка связана с инструментами, возвращаем понятное сообщение
                if error_code == "mcp_error" or "mcp" in error_message.lower():
                    return {"user_message": f"⚠️ Ошибка подключения к инструментам: {error_message}\n\nПопробуйте позже или обратитесь к администратору."}
                
                # Если это Internal server error или Empty response from API, делаем повторную попытку
                if self._is_internal_server_error(error_message):
                    logger.warning(f"Обнаружена ошибка {error_message}, делаем повторную попытку", chat_id)
                    return await self._retry_internal_server_error(chat_id, user_text, error_message)
                
                return {"user_message": f"⚠️ Ошибка API: {error_message}"}
            
            # API возвращает объект с полем output
            if "output" in result and isinstance(result["output"], list) and len(result["output"]) > 0:
                # Ищем текстовое сообщение в output (не mcp_list_tools)
                # Берем последнее сообщение, пропуская технические JSON
                for output_item in reversed(result["output"]):
                    if output_item.get("type") == "message" and "content" in output_item:
                        content = output_item["content"]
                        if content and len(content) > 0:
                            text_content = content[0].get("text", "")
                            # Пропускаем JSON-ответы (содержат фигурные скобки и ключи)
                            if not text_content.strip().startswith("{") and not "stage" in text_content:
                                response_text = text_content
                                break
            
            if not response_text:
                # Если нет текста, но есть ошибка, показываем её
                if "error" in result and result["error"]:
                    error_info = result["error"]
                    error_message = error_info.get("message", "Неизвестная ошибка")
                    return {"user_message": f"⚠️ Ошибка: {error_message}"}
                else:
                    # Если это Empty response from API, делаем повторную попытку
                    error_message = "Empty response from API"
                    logger.warning("Обнаружена ошибка Empty response from API, делаем повторную попытку", chat_id)
                    return await self._retry_internal_server_error(chat_id, user_text, error_message)
            
            # Сохраняем новый response_id в YDB через executor (не блокирует event loop)
            if response_id:
                await asyncio.to_thread(
                    self.ydb_client.save_response_id,
                    chat_id,
                    response_id
                )
                logger.ydb("Сохранен response_id", chat_id)
            
            # Логируем метрики
            latency = time.time() - start_time
            logger.api("Запрос выполнен", latency, response_id)
            
            final_text = response_text
            if final_text.strip().startswith('[CALL_MANAGER]'):
                return self.escalation_service.handle(final_text, chat_id)
            return {"user_message": final_text}
            
        except Exception as e:
            error_msg = str(e)
            logger.error("Ошибка при работе с API", error_msg)
            
            # Если это Internal server error или Empty response from API, делаем повторную попытку
            if self._is_internal_server_error(error_msg):
                logger.warning(f"Обнаружена ошибка {error_msg} в исключении, делаем повторную попытку", chat_id)
                return await self._retry_internal_server_error(chat_id, user_text, error_msg)
            
            # Если ошибка связана с цепочкой (слишком длинная/просрочена), очищаем контекст
            if any(keyword in error_msg.lower() for keyword in ["chain", "expired", "too long", "цепочка", "просрочена"]):
                logger.warning("Очищаем контекст из-за ошибки цепочки", chat_id)
                await self.reset_context(chat_id)
                
                # Повторяем запрос без previous_response_id
                try:
                    # Добавляем московское время в начало сообщения для повторного запроса
                    moscow_time = self._get_moscow_time()
                    input_with_time = f"[{moscow_time}] {user_text}"
                    
                    payload = {
                        "prompt": {
                            "id": self.agent_id,
                            "variables": {}
                        },
                        "input": input_with_time,
                        "chat_options": {
                            "chat_id": chat_id
                        },
                        "tool_choice": "none"  # Отключаем инструменты при ошибке
                    }
                    
                    # Сохраняем повторный запрос для дебага через executor
                    await asyncio.to_thread(
                        self.debug_service.save_request,
                        payload,
                        f"{chat_id}_retry"
                    )
                    
                    result = await self._retry_with_backoff(
                        lambda: self._make_api_request(payload)
                    )
                    
                    # Сохраняем ответ от LLM для дебага (retry) через executor
                    await asyncio.to_thread(
                        self.debug_service.save_response,
                        result,
                        f"{chat_id}_retry"
                    )
                    
                    response_id = result.get("id")
                    response_text = ""
                    
                    # API возвращает объект с полем output
                    if "output" in result and isinstance(result["output"], list) and len(result["output"]) > 0:
                        # Ищем текстовое сообщение в output (не mcp_list_tools)
                        # Берем последнее сообщение, пропуская технические JSON
                        for output_item in reversed(result["output"]):
                            if output_item.get("type") == "message" and "content" in output_item:
                                content = output_item["content"]
                                if content and len(content) > 0:
                                    text_content = content[0].get("text", "")
                                    # Пропускаем JSON-ответы (содержат фигурные скобки и ключи)
                                    if not text_content.strip().startswith("{") and not "stage" in text_content:
                                        response_text = text_content
                                        break
                    
                    if response_id:
                        await asyncio.to_thread(
                            self.ydb_client.save_response_id,
                            chat_id,
                            response_id
                        )
                        logger.ydb("Сохранен response_id (retry)", chat_id)
                    
                    logger.success("Повторный запрос выполнен успешно", chat_id)
                    final_text = response_text
                    if final_text.strip().startswith('[CALL_MANAGER]'):
                        return self.escalation_service.handle(final_text, chat_id)
                    return {"user_message": final_text}
                    
                except Exception as retry_error:
                    logger.error("Ошибка при повторном запросе", str(retry_error))
                    return {"user_message": f"Ошибка при повторном запросе: {str(retry_error)}"}
            
            return {"user_message": f"Ошибка при работе с Responses API: {error_msg}"}
    
    async def send_to_agent(self, chat_id: str, user_text: str) -> dict:
        """Отправка сообщения агенту через LangGraph (основной метод)"""
        # Используем LangGraph как основной метод
        try:
            return await self.send_to_agent_langgraph(chat_id, user_text)
        except Exception as e:
            logger.error(f"Ошибка в LangGraph, fallback к Responses API: {e}", chat_id)
            # Fallback к старому методу только при критической ошибке
            return await self._send_to_agent_responses_api(chat_id, user_text)
    
    async def reset_context(self, chat_id: str):
        """Сброс контекста для чата (асинхронный, не блокирует event loop)"""
        try:
            # Сбрасываем и previous_response_id, и thread_id
            await asyncio.to_thread(
                self.ydb_client.reset_context,
                chat_id
            )
            await asyncio.to_thread(
                self.ydb_client.reset_thread,
                chat_id
            )
            logger.ydb("Контекст сброшен", chat_id)
        except Exception as e:
            logger.error("Ошибка при сбросе контекста", str(e))