"""
Orchestrator для обработки диалогов через Responses API
"""
import json
from typing import List, Dict, Any, Optional
from .client import ResponsesAPIClient
from .tools_registry import ResponsesToolsRegistry
from .config import ResponsesAPIConfig
from ..logger_service import logger

# Импортируем CallManagerException один раз, а не в цикле
try:
    from ...agents.tools.call_manager_tools import CallManagerException
except ImportError:
    CallManagerException = None


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
        
        # Получаем схемы инструментов один раз (не меняются в процессе выполнения)
        tools_schemas = self.tools_registry.get_all_tools_schemas()
        
        # Цикл для обработки множественных вызовов инструментов
        # API может вызывать инструменты несколько раз подряд
        max_iterations = 10  # Максимальное количество итераций для предотвращения бесконечного цикла
        iteration = 0
        tool_calls_info = []
        reply_text = ""
        
        while iteration < max_iterations:
            iteration += 1
            logger.debug(f"Итерация {iteration}: Запрос к API (сообщений в истории: {len(conversation_history)})")
            
            # Запрос к модели
            try:
                response = self.client.create_response(
                    instructions=self.instructions,
                    input_messages=conversation_history,
                    tools=tools_schemas if tools_schemas else None,
                )
            except Exception as e:
                logger.error(f"Ошибка при запросе к API на итерации {iteration}: {e}", exc_info=True)
                # Если это критическая ошибка, прекращаем цикл
                break
            
            # Логируем ответ только на уровне DEBUG (избыточно для INFO)
            logger.debug(f"ОТВЕТ ОТ RESPONSES API (итерация {iteration}): output_text={bool(getattr(response, 'output_text', None))}, output_len={len(getattr(response, 'output', []))}")
            
            # Проверяем, есть ли готовый текст ответа
            if hasattr(response, "output_text") and response.output_text:
                reply_text = response.output_text
                logger.info(f"Получен текстовый ответ на итерации {iteration} (длина: {len(reply_text)})")
                break
            
            # Обрабатываем tool_calls
            tool_calls = self._extract_tool_calls(response)
            
            if not tool_calls:
                # Если нет tool_calls, но и нет output_text, прекращаем цикл
                logger.warning(f"Нет tool_calls и нет output_text на итерации {iteration}")
                break
            
            logger.debug(f"Найдено {len(tool_calls)} вызовов инструментов на итерации {iteration}")
            
            # Выполняем инструменты
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
                    self._add_tool_call_to_history(
                        conversation_history, tool_calls_info, 
                        func_name, call_id, args_json, args, result
                    )
                    
                except Exception as e:
                    # Проверяем, не является ли это CallManagerException
                    if CallManagerException and isinstance(e, CallManagerException):
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
                    
                    # Обрабатываем ошибку инструмента
                    logger.error(f"Ошибка при вызове инструмента {func_name}: {e}", exc_info=True)
                    error_result = f"Ошибка при выполнении инструмента: {str(e)}"
                    self._add_tool_call_to_history(
                        conversation_history, tool_calls_info,
                        func_name, call_id, args_json, args, error_result
                    )
        
        if iteration >= max_iterations:
            logger.warning(f"Достигнут лимит итераций ({max_iterations}). Прекращаем цикл.")
        
        if not reply_text:
            logger.warning(f"Не получен текстовый ответ после {iteration} итераций")
        
        logger.debug(f"Финальный результат: итераций={iteration}, длина ответа={len(reply_text) if reply_text else 0}, инструментов={len(tool_calls_info)}")
        
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
    
    def _add_tool_call_to_history(
        self,
        conversation_history: List[Dict[str, Any]],
        tool_calls_info: List[Dict[str, Any]],
        func_name: str,
        call_id: str,
        args_json: str,
        args: Dict[str, Any],
        result: Any
    ) -> None:
        """
        Добавление вызова инструмента в историю разговора
        
        Args:
            conversation_history: История разговора
            tool_calls_info: Список информации о вызовах инструментов
            func_name: Имя функции
            call_id: ID вызова
            args_json: Аргументы в формате JSON (строка)
            args: Аргументы (словарь)
            result: Результат выполнения инструмента
        """
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
        conversation_history.append(tool_output)

