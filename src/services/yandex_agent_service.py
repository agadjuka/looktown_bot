"""
Модуль для работы с Responses API и памятью через previous_response_id
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


class YandexAgentService:
    """Сервис для работы с Responses API"""
    
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
        
        # Кэш для времени (обновляем раз в минуту)
        self._time_cache = None
        self._time_cache_timestamp = 0
    
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
        Проверяет, является ли ошибка "Internal server error".
        
        :param error_message: Текст ошибки
        :return: True, если это Internal server error
        """
        error_lower = error_message.lower()
        return "internal server error" in error_lower

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
        Выполняет повторную попытку при ошибке Internal server error.
        Если повторная попытка тоже возвращает ошибку, отправляет менеджер-алерт.
        
        :param chat_id: ID чата
        :param user_text: Исходное сообщение пользователя
        :param first_error_message: Сообщение об ошибке из первой попытки
        :return: Словарь с ответом для пользователя и менеджер-алертом (если нужно)
        """
        try:
            logger.info("Выполняем повторную попытку при Internal server error", chat_id)
            
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
                
                # Если повторная попытка тоже вернула Internal server error, отправляем менеджер-алерт
                if self._is_internal_server_error(error_message):
                    logger.error("Повторная попытка тоже вернула Internal server error, отправляем менеджер-алерт", chat_id)
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
                    return {"user_message": f"⚠️ Ошибка: {error_message}"}
                else:
                    raise Exception("Empty response from API")
            
            # Сохраняем response_id
            if response_id:
                await asyncio.to_thread(
                    self.ydb_client.save_response_id,
                    chat_id,
                    response_id
                )
                logger.ydb("Сохранен response_id (retry ISE)", chat_id)
            
            logger.success("Повторная попытка при Internal server error выполнена успешно", chat_id)
            
            # Проверяем на эскалацию
            final_text = response_text
            if final_text.strip().startswith('[CALL_MANAGER]'):
                return self.escalation_service.handle(final_text, chat_id)
            return {"user_message": final_text}
            
        except Exception as retry_error:
            error_msg = str(retry_error)
            logger.error("Ошибка при повторной попытке Internal server error", error_msg)
            
            # Если повторная попытка тоже вернула Internal server error, отправляем менеджер-алерт
            if self._is_internal_server_error(error_msg):
                logger.error("Повторная попытка тоже вернула Internal server error в исключении, отправляем менеджер-алерт", chat_id)
                return self.escalation_service.handle_api_error(
                    error_msg,
                    chat_id,
                    user_text
                )
            
            # Если другая ошибка, возвращаем её
            return {"user_message": f"Ошибка при повторном запросе: {error_msg}"}
    
    async def send_to_agent(self, chat_id: str, user_text: str) -> dict:
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
                
                # Если это Internal server error, делаем повторную попытку
                if self._is_internal_server_error(error_message):
                    logger.warning("Обнаружена ошибка Internal server error, делаем повторную попытку", chat_id)
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
                    raise Exception("Empty response from API")
            
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
            
            # Если это Internal server error, делаем повторную попытку
            if self._is_internal_server_error(error_msg):
                logger.warning("Обнаружена ошибка Internal server error в исключении, делаем повторную попытку", chat_id)
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
    
    async def reset_context(self, chat_id: str):
        """Сброс контекста для чата (асинхронный, не блокирует event loop)"""
        try:
            await asyncio.to_thread(
                self.ydb_client.reset_context,
                chat_id
            )
            logger.ydb("Контекст сброшен", chat_id)
        except Exception as e:
            logger.error("Ошибка при сбросе контекста", str(e))