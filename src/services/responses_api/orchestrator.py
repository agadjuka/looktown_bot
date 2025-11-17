"""
Orchestrator для обработки диалогов через Responses API
"""
import json
from typing import List, Dict, Any, Optional
from .client import ResponsesAPIClient
from .tools_registry import ResponsesToolsRegistry
from .config import ResponsesAPIConfig
from ..logger_service import logger


class ResponsesOrchestrator:
    """Orchestrator для обработки диалогов через Responses API"""
    
    def __init__(
        self,
        instructions: str,
        tools_registry: Optional[ResponsesToolsRegistry] = None,
        client: Optional[ResponsesAPIClient] = None,
        config: Optional[ResponsesAPIConfig] = None,
    ):
        """
        Инициализация orchestrator
        
        Args:
            instructions: Системные инструкции для ассистента
            tools_registry: Регистрация инструментов (если None, создаётся пустая)
            client: Клиент Responses API (если None, создаётся новый)
            config: Конфигурация (если None, создаётся новая)
        """
        self._last_conversation_history = None
        self.instructions = instructions
        self.tools_registry = tools_registry or ResponsesToolsRegistry()
        self.config = config or ResponsesAPIConfig()
        self.client = client or ResponsesAPIClient(self.config)
    
    def run_turn(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Один полный ход диалога
        
        Args:
            user_message: Сообщение пользователя
            conversation_history: История диалога (если None, создаётся новая)
            
        Returns:
            Словарь с ключами:
                - reply: Текст ответа для пользователя
                - conversation_history: Обновлённая история диалога
                - tool_calls: Список вызовов инструментов (если были)
        """
        if conversation_history is None:
            conversation_history = []
        
        # Добавляем сообщение пользователя в историю
        conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Получаем схемы инструментов
        tools_schemas = self.tools_registry.get_all_tools_schemas()
        
        # Первый запрос к модели
        response = self.client.create_response(
            instructions=self.instructions,
            input_messages=conversation_history,
            tools=tools_schemas if tools_schemas else None,
        )
        
        # ЛОГИРУЕМ ПОЛНЫЙ ОТВЕТ ДЛЯ ДИАГНОСТИКИ
        logger.info("=" * 80)
        logger.info("ПОЛНЫЙ ОТВЕТ ОТ RESPONSES API:")
        logger.info(f"Тип response: {type(response)}")
        logger.info(f"Атрибуты response: {dir(response)}")
        if hasattr(response, "_data"):
            logger.info(f"response._data: {response._data}")
        if hasattr(response, "output_text"):
            logger.info(f"response.output_text: {repr(response.output_text)}")
        if hasattr(response, "output"):
            logger.info(f"response.output: {repr(response.output)}")
            logger.info(f"Тип response.output: {type(response.output)}")
        logger.info("=" * 80)
        
        # Проверяем, есть ли готовый текст ответа
        if hasattr(response, "output_text") and response.output_text:
            return {
                "reply": response.output_text,
                "conversation_history": conversation_history,
                "tool_calls": [],
            }
        
        # Обрабатываем tool_calls
        tool_calls = self._extract_tool_calls(response)
        
        if not tool_calls:
            # Если нет tool_calls, но и нет output_text, возвращаем пустой ответ
            return {
                "reply": "",
                "conversation_history": conversation_history,
                "tool_calls": [],
            }
        
        # Выполняем инструменты
        tool_outputs = []
        tool_calls_info = []
        
        for call in tool_calls:
            func_name = call.get("name")
            call_id = call.get("call_id", "")
            args_json = call.get("arguments", "{}")
            
            try:
                args = json.loads(args_json) if isinstance(args_json, str) else args_json
            except json.JSONDecodeError:
                logger.error(f"Ошибка парсинга аргументов для {func_name}: {args_json}")
                args = {}
            
            # Вызываем инструмент
            try:
                result = self.tools_registry.call_tool(func_name, args)
                
                # Сохраняем информацию о вызове
                tool_calls_info.append({
                    "name": func_name,
                    "args": args,
                    "result": result,
                })
                
                # Добавляем function_call в историю
                conversation_history.append({
                    "type": "function_call",
                    "call_id": call_id,
                    "name": func_name,
                    "arguments": args_json if isinstance(args_json, str) else json.dumps(args_json),
                })
                
                # Добавляем результат в историю
                tool_output = {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result,
                }
                tool_outputs.append(tool_output)
                conversation_history.append(tool_output)
                
            except Exception as e:
                # Проверяем, не является ли это CallManagerException
                from ...agents.tools.call_manager_tools import CallManagerException
                if isinstance(e, CallManagerException):
                    # CallManager был вызван - возвращаем специальный результат
                    escalation_result = e.escalation_result
                    logger.info(f"CallManager вызван через инструмент {func_name}")
                    
                    return {
                        "reply": escalation_result.get("user_message", "Секундочку, уточняю ваш вопрос у менеджера."),
                        "conversation_history": conversation_history,
                        "tool_calls": tool_calls_info,
                        "call_manager": True,
                        "manager_alert": escalation_result.get("manager_alert"),
                    }
                
                logger.error(f"Ошибка при вызове инструмента {func_name}: {e}", exc_info=True)
                error_result = f"Ошибка при выполнении инструмента: {str(e)}"
                
                tool_calls_info.append({
                    "name": func_name,
                    "args": args,
                    "result": error_result,
                })
                
                tool_output = {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": error_result,
                }
                tool_outputs.append(tool_output)
                conversation_history.append(tool_output)
        
        # Второй запрос к модели с результатами инструментов
        response2 = self.client.create_response(
            instructions=self.instructions,
            input_messages=conversation_history,
            tools=tools_schemas if tools_schemas else None,
        )
        
        # Получаем финальный ответ
        reply_text = getattr(response2, "output_text", "")
        
        # Сохраняем conversation_history для последующего использования
        self._last_conversation_history = conversation_history
        
        return {
            "reply": reply_text,
            "conversation_history": conversation_history,
            "tool_calls": tool_calls_info,
        }
    
    def _extract_tool_calls(self, response: Any) -> List[Dict[str, Any]]:
        """
        Извлечение tool_calls из ответа Responses API
        
        Args:
            response: Ответ от Responses API
            
        Returns:
            Список tool_calls
        """
        tool_calls = []
        
        # Проверяем наличие output в ответе
        if not hasattr(response, "output"):
            return tool_calls
        
        output = response.output
        if not output:
            return tool_calls
        
        # Обрабатываем каждый элемент output
        for item in output:
            # item может быть словарём, а не объектом
            if isinstance(item, dict):
                item_type = item.get("type")
                if item_type == "function_call":
                    tool_call = {
                        "name": item.get("name", ""),
                        "call_id": item.get("call_id", ""),
                        "arguments": item.get("arguments", "{}"),
                    }
                    tool_calls.append(tool_call)
            elif hasattr(item, "type"):
                if item.type == "function_call":
                    tool_call = {
                        "name": getattr(item, "name", ""),
                        "call_id": getattr(item, "call_id", ""),
                        "arguments": getattr(item, "arguments", "{}"),
                    }
                    tool_calls.append(tool_call)
        
        return tool_calls

