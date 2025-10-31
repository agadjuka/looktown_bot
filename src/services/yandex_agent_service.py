"""
Модуль для работы с Responses API и памятью через previous_response_id
"""
import os
import time
import random
import requests
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
    
    def _get_moscow_time(self) -> str:
        """Получить текущую дату и время в московском часовом поясе"""
        moscow_tz = pytz.timezone('Europe/Moscow')
        moscow_time = datetime.now(moscow_tz)
        return moscow_time.strftime("%d.%m.%Y %H:%M:%S")
    
    def _retry_with_backoff(self, func, max_retries=3):
        """Ретраи с экспоненциальным backoff"""
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                
                # Экспоненциальный backoff с джиттером
                delay = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(delay)
    
    def _make_api_request(self, payload: dict) -> dict:
        """Выполнение запроса к Responses API"""
        # Пытаемся использовать IAM токен (для инструментов)
        try:
            if self.auth_service.is_service_account_configured():
                iam_token = self.auth_service.get_iam_token()
                headers = {
                    "Authorization": f"Bearer {iam_token}",
                    "Content-Type": "application/json"
                }
                logger.debug("Используем Bearer токен (IAM)")
            else:
                raise ValueError("Сервисный аккаунт не настроен")
        except Exception as e:
            logger.debug("Fallback к API ключу", str(e))
            # Fallback к API ключу
            headers = {
                "Authorization": f"Api-Key {self.auth_service.get_api_key()}",
                "x-folder-id": os.getenv("YANDEX_FOLDER_ID"),
                "Content-Type": "application/json"
            }
        
        # Полный URL с путем /responses
        full_url = f"{self.base_url}/responses"
        
        response = requests.post(
            full_url,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"API request failed with status {response.status_code}: {response.text}")
        
        return response.json()
    
    def send_to_agent(self, chat_id: str, user_text: str) -> dict:
        """Отправка сообщения агенту через Responses API с памятью"""
        try:
            start_time = time.time()
            
            # Получаем last_response_id из YDB
            previous_response_id = self.ydb_client.get_last_response_id(chat_id)
            
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
            
            # Сохраняем запрос для дебага
            self.debug_service.save_request(payload, chat_id)
            
            # Выполняем запрос с ретраями
            def make_request():
                return self._make_api_request(payload)
            
            result = self._retry_with_backoff(make_request)
            
            # Сохраняем ответ от LLM для дебага
            self.debug_service.save_response(result, chat_id)
            
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
                else:
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
            
            # Сохраняем новый response_id в YDB
            if response_id:
                self.ydb_client.save_response_id(chat_id, response_id)
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
            
            # Если ошибка связана с цепочкой (слишком длинная/просрочена), очищаем контекст
            if any(keyword in error_msg.lower() for keyword in ["chain", "expired", "too long", "цепочка", "просрочена"]):
                logger.warning("Очищаем контекст из-за ошибки цепочки", chat_id)
                self.reset_context(chat_id)
                
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
                    
                    # Сохраняем повторный запрос для дебага
                    self.debug_service.save_request(payload, f"{chat_id}_retry")
                    
                    result = self._retry_with_backoff(lambda: self._make_api_request(payload))
                    
                    # Сохраняем ответ от LLM для дебага (retry)
                    self.debug_service.save_response(result, f"{chat_id}_retry")
                    
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
                        self.ydb_client.save_response_id(chat_id, response_id)
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
    
    def reset_context(self, chat_id: str):
        """Сброс контекста для чата"""
        try:
            self.ydb_client.reset_context(chat_id)
            logger.ydb("Контекст сброшен", chat_id)
        except Exception as e:
            logger.error("Ошибка при сбросе контекста", str(e))