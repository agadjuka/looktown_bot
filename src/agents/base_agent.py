"""
Базовый класс для агентов
"""
import json
from datetime import datetime
from typing import Optional, Dict, Any
from yandex_cloud_ml_sdk._threads.thread import Thread
from yandex_cloud_ml_sdk._assistants.assistant import Assistant
from ..services.langgraph_service import LangGraphService
from ..services.logger_service import logger
from ..services.llm_request_logger import llm_request_logger
from ..services.tool_history_service import get_tool_history_service


class BaseAgent:
    """Базовый класс для всех агентов"""
    
    def __init__(
        self,
        langgraph_service: LangGraphService,
        instruction: str,
        tools: list = None,
        assistant: Optional[Assistant] = None,
        agent_name: str = None
    ):
        self.langgraph_service = langgraph_service
        self.instruction = instruction
        self.agent_name = agent_name or self.__class__.__name__
        
        if assistant:
            self.assistant = assistant
            # Если assistant передан извне, получаем инструменты из него
            # и сохраняем классы инструментов для вызова (если они были переданы)
            if tools:
                self.tools = {x.__name__: x for x in tools}
            else:
                self.tools = {}
            # Получаем объекты SDK инструментов из assistant
            self.sdk_tools = getattr(assistant, 'tools', [])
        else:
            # Создаём инструменты
            tool_list = []
            if tools:
                # Сохраняем классы инструментов для вызова
                self.tools = {x.__name__: x for x in tools}
                # Создаём объекты SDK инструментов для передачи в Assistant и логирования
                tool_list = [langgraph_service.sdk.tools.function(x) for x in tools]
                # Сохраняем объекты SDK инструментов для логирования
                self.sdk_tools = tool_list
            else:
                self.tools = {}
                self.sdk_tools = []
            
            # Создаём Assistant с именем (или используем существующего)
            self.assistant = langgraph_service.get_or_create_assistant(
                instruction=instruction,
                tools=tool_list,
                name=self.agent_name
            )
        
        # Инициализируем список для отслеживания tool_calls
        self._last_tool_calls = []
        
        # Результат CallManager (если был вызван)
        self._call_manager_result = None
    
    def __call__(self, message: str, thread: Thread) -> str:
        """
        Выполнение запроса к агенту
        
        :param message: Сообщение для агента
        :param thread: Thread для выполнения запроса
        :return: Ответ агента
        """
        return self._execute_request(message, thread, message_added=False)
    
    def _execute_request(self, message: str, thread: Thread, message_added: bool = False) -> str:
        """
        Внутренний метод для выполнения запроса к агенту
        
        :param message: Сообщение для агента
        :param thread: Thread для выполнения запроса
        :param message_added: Флаг, указывающий, было ли сообщение уже добавлено в thread
        :return: Ответ агента
        """
        try:
            # Очищаем предыдущие tool_calls
            self._last_tool_calls = []
            
            # Добавляем сообщение в Thread только если оно еще не было добавлено (при retry не дублируем)
            if not message_added:
                # Получаем chat_id из thread (если он был сохранен)
                chat_id = getattr(thread, 'chat_id', None)
                
                # Если есть chat_id, добавляем историю результатов инструментов в контекст
                if chat_id:
                    try:
                        tool_history_service = get_tool_history_service()
                        tool_history_context = tool_history_service.format_tool_results_for_context(chat_id)
                        
                        if tool_history_context:
                            # Добавляем историю результатов инструментов в thread перед сообщением пользователя
                            # Это поможет агенту использовать результаты из предыдущих циклов
                            thread.write(f"[Контекст из предыдущих циклов]\n{tool_history_context}")
                            logger.debug(f"Добавлена история результатов инструментов в контекст для chat_id={chat_id}")
                    except Exception as e:
                        logger.debug(f"Ошибка при добавлении истории результатов инструментов в контекст: {e}")
                
                # Логируем сообщение пользователя ПЕРЕД добавлением в thread
                thread_id = getattr(thread, 'id', None)
                # Логируем реальное сообщение пользователя
                llm_request_logger.start_new_request()  # Начинаем новый запрос
                timestamp = datetime.now().isoformat()
                log_entry = f"\n{'='*80}\n"
                log_entry += f"[{timestamp}] USER MESSAGE (EXACT DATA SENT TO API)\n"
                log_entry += f"{'='*80}\n"
                if thread_id:
                    log_entry += f"Thread ID: {thread_id}\n"
                log_entry += f"Message:\n{message}\n"
                llm_request_logger._write_raw(log_entry)
                # Добавляем сообщение в thread (это то, что реально отправляется в LLM)
                thread.write(message)
            
            # Получаем контекст thread ПОСЛЕ добавления сообщения - это то, что реально отправляется в LLM
            thread_messages = []
            try:
                thread_messages = list(thread) if hasattr(thread, '__iter__') else []
            except Exception as e:
                logger.debug(f"Не удалось получить сообщения thread: {e}")
            
            # Получаем instruction и tools для логирования
            instruction = self.instruction
            # Для логирования используем исходные классы инструментов, чтобы получить их JSON схемы
            # SDK объекты не дают прямого доступа к схеме, поэтому используем исходные классы
            tool_classes = list(self.tools.values()) if self.tools else []
            sdk_tools = getattr(self, 'sdk_tools', [])
            
            # Логируем реальный запрос к LLM - то, что реально отправляется через API
            thread_id = getattr(thread, 'id', None)
            assistant_id = getattr(self.assistant, 'id', None)
            llm_request_logger.log_request_to_llm(
                agent_name=self.agent_name,
                thread_id=thread_id,
                assistant_id=assistant_id,
                instruction=instruction,
                tools=tool_classes,  # Передаем классы для извлечения JSON схемы
                messages=thread_messages
            )
            
            # Запускаем Assistant
            run = self.assistant.run(thread)
            logger.debug(f"Запущен run для агента {self.agent_name}, run_id: {run.id if hasattr(run, 'id') else 'N/A'}")
            
            res = run.wait()
            
            # Логируем реальный ответ от LLM - то, что реально получено от API
            try:
                res_text = getattr(res, 'text', None) if res else None
                res_tool_calls = getattr(res, 'tool_calls', None) if res else None
                
                llm_request_logger.log_response_from_llm(
                    agent_name=self.agent_name,
                    response_text=res_text,
                    tool_calls=res_tool_calls if res_tool_calls else None,
                    raw_response=res
                )
            except Exception as e:
                logger.debug(f"Ошибка при логировании ответа LLM: {e}")
            
            # Детальное логирование результата для диагностики
            logger.debug(f"Результат run.wait() для агента {self.agent_name}:")
            logger.debug(f"  - Тип res: {type(res)}")
            logger.debug(f"  - res is None: {res is None}")
            
            if res is None:
                error_msg = "Run завершился без результата (res is None)"
                logger.error(f"Ошибка в агенте {self.agent_name}: {error_msg}")
                logger.error(f"Детали: run_id={getattr(run, 'id', 'N/A')}, message={message[:100]}")
                raise RuntimeError("run is failed and don't have a message result")
            
            # Проверяем статус через безопасные атрибуты (не вызывающие исключения)
            res_is_failed = getattr(res, 'is_failed', False)
            res_status = getattr(res, 'status', None)
            res_status_name = getattr(res, 'status_name', None)
            res_error = getattr(res, 'error', None)
            
            logger.debug(f"  - Атрибуты res: {[attr for attr in dir(res) if not attr.startswith('_')]}")
            logger.debug(f"  - res.is_failed: {res_is_failed}")
            logger.debug(f"  - res.status: {res_status}")
            logger.debug(f"  - res.status_name: {res_status_name}")
            if res_error:
                logger.debug(f"  - res.error: {res_error}")
            
            # Логируем информацию о run объекте
            try:
                run_info = {
                    'id': getattr(run, 'id', 'N/A'),
                    'assistant_id': getattr(run, 'assistant_id', 'N/A'),
                    'thread_id': getattr(run, 'thread_id', 'N/A'),
                }
                # Пытаемся получить статус через разные способы
                if hasattr(run, 'status'):
                    run_info['status'] = run.status
                elif hasattr(run, '_status'):
                    run_info['status'] = run._status
                logger.debug(f"  - Информация о run: {run_info}")
            except Exception as e:
                logger.debug(f"  - Не удалось получить информацию о run: {e}")
            
            # Проверяем результат после первого wait()
            # Если run завершился с ошибкой, проверяем через is_failed или status
            if res_is_failed:
                error_msg = f"Run завершился с ошибкой (is_failed=True, status={res_status}, status_name={res_status_name})"
                logger.error(f"Ошибка в агенте {self.agent_name}: {error_msg}")
                logger.error(f"Детали: run_id={getattr(run, 'id', 'N/A')}, message={message[:200]}")
                if res_error:
                    logger.error(f"Ошибка run: {res_error}")
                # Создаем исключение с информацией об ошибке для проверки типа
                runtime_error = RuntimeError("run is failed and don't have a message result")
                runtime_error.res_error = res_error  # Сохраняем res_error для проверки
                raise runtime_error
            
            # Только после проверки статуса пытаемся получить text
            try:
                res_text = res.text
                logger.debug(f"  - res.text: {repr(res_text[:200]) if res_text else 'None/Empty'}")
            except (ValueError, AttributeError) as e:
                error_msg = f"Не удалось получить res.text: {e}"
                logger.error(f"Ошибка в агенте {self.agent_name}: {error_msg}")
                logger.error(f"Детали: run_id={getattr(run, 'id', 'N/A')}, is_failed={res_is_failed}, status={res_status}")
                raise RuntimeError("run is failed and don't have a message result")
            
            # Проверяем tool_calls безопасно
            res_tool_calls = getattr(res, 'tool_calls', None)
            logger.debug(f"  - res.tool_calls: {res_tool_calls}")
            logger.debug(f"  - res.tool_calls is None: {res_tool_calls is None}")
            logger.debug(f"  - res.tool_calls is empty: {res_tool_calls == [] if res_tool_calls is not None else 'N/A'}")
            
            # Обрабатываем JSON с инструментами в цикле, пока они не закончатся
            # Это нужно, потому что SDK иногда возвращает инструменты в виде JSON в res.text вместо res.tool_calls
            max_json_iterations = 10  # Защита от бесконечного цикла
            json_iteration = 0
            
            while json_iteration < max_json_iterations:
                json_iteration += 1
                
                # Проверяем, не является ли res.text JSON-описанием инструмента
                # Если да, то это промежуточная стадия и нужно продолжить обработку
                if res_tool_calls is None or (isinstance(res_tool_calls, list) and len(res_tool_calls) == 0):
                    try:
                        res_text_check = res.text
                        if res_text_check:
                            # Проверяем, не является ли это JSON с описанием инструмента
                            try:
                                parsed_json = json.loads(res_text_check)
                                if isinstance(parsed_json, dict):
                                    # Проверяем два случая:
                                    # 1. JSON с полем 'tool' - явный вызов инструмента
                                    # 2. JSON с полем 'reason' - попытка вызвать CallManager
                                    tool_name = None
                                    tool_args = {}
                                    
                                    if 'tool' in parsed_json:
                                        tool_name = parsed_json.get('tool')
                                        tool_args = parsed_json.get('arguments', {})
                                    elif 'reason' in parsed_json and 'CallManager' in self.tools:
                                        # Модель пытается вызвать CallManager через JSON
                                        tool_name = 'CallManager'
                                        tool_args = {'reason': parsed_json.get('reason', 'Не указана причина')}
                                        logger.warning(f"Обнаружен JSON с полем 'reason' - интерпретируем как вызов CallManager")
                                    
                                    if tool_name:
                                        logger.warning(f"Обнаружен JSON с инструментом в res.text (итерация {json_iteration}), но res.tool_calls пустой.")
                                        logger.warning(f"Инструмент: {tool_name}, аргументы: {tool_args}")
                                        
                                        # Если инструмент есть в списке доступных, вызываем его вручную
                                        # Проверяем регистронезависимо, так как SDK может возвращать lowercase
                                        tool_found = None
                                        
                                        # Сначала пробуем точное совпадение
                                        if tool_name in self.tools:
                                            tool_found = tool_name
                                        else:
                                            # Пробуем найти регистронезависимо
                                            for key in self.tools.keys():
                                                if key.lower() == tool_name.lower():
                                                    tool_found = key
                                                    break
                                        
                                        if tool_found:
                                            logger.info(f"Вызываем инструмент {tool_found} вручную из JSON (запрошен как {tool_name})")
                                            fn = self.tools[tool_found]
                                            try:
                                                obj = fn(**tool_args)
                                                try:
                                                    tool_result = obj.process(thread) if hasattr(obj, 'process') else str(obj)
                                                except Exception as process_e:
                                                    # Проверяем, не является ли это CallManagerException
                                                    from .tools.call_manager_tools import CallManagerException
                                                    if isinstance(process_e, CallManagerException):
                                                        # Сохраняем результат CallManager и прекращаем работу агента
                                                        self._call_manager_result = process_e.escalation_result
                                                        logger.info(f"CallManager вызван через JSON (исключение в process), прекращаем работу агента {self.agent_name}")
                                                        # Прерываем обработку - пропускаем дальнейший код в этом блоке
                                                        raise process_e  # Пробрасываем исключение, чтобы выйти из try блока
                                                    else:
                                                        raise  # Пробрасываем другие исключения
                                                
                                                # Сохраняем информацию о вызове (выполнится только если CallManager не был вызван)
                                                self._last_tool_calls.append({
                                                    "name": tool_found,
                                                    "args": tool_args,
                                                    "result": tool_result
                                                })
                                                
                                                # Логируем результаты инструментов перед отправкой в LLM
                                                tool_result_data = [{"name": tool_found, "content": tool_result}]
                                                try:
                                                    llm_request_logger.log_tool_results_to_llm(
                                                        agent_name=self.agent_name,
                                                        tool_results=tool_result_data
                                                    )
                                                except Exception as e:
                                                    logger.debug(f"Ошибка при логировании результатов инструментов: {e}")
                                                
                                                # Когда SDK возвращает инструмент в JSON вместо tool_calls,
                                                # submit_tool_results не работает, потому что SDK не знает, к какому вызову относится результат.
                                                # Вместо этого добавляем результат инструмента в thread как сообщение пользователя,
                                                # а затем запускаем новый run, чтобы агент увидел результат и продолжил работу.
                                                logger.info(f"Добавляем результат инструмента {tool_found} в thread и запускаем новый run")
                                                
                                                # Формируем сообщение с результатом инструмента
                                                tool_result_message = f"Результат выполнения инструмента {tool_found}:\n{tool_result}"
                                                
                                                # Добавляем результат в thread
                                                thread.write(tool_result_message)
                                                
                                                # Запускаем новый run с результатом инструмента в контексте
                                                run = self.assistant.run(thread)
                                                logger.debug(f"Запущен новый run после вызова инструмента {tool_found}, run_id: {run.id if hasattr(run, 'id') else 'N/A'}")
                                                
                                                # Получаем следующий ответ от агента
                                                res = run.wait()
                                                
                                                # Логируем ответ от LLM после отправки результатов инструментов
                                                try:
                                                    res_text = getattr(res, 'text', None) if res else None
                                                    res_tool_calls = getattr(res, 'tool_calls', None) if res else None
                                                    llm_request_logger.log_response_from_llm(
                                                        agent_name=self.agent_name,
                                                        response_text=res_text,
                                                        tool_calls=res_tool_calls if res_tool_calls else None,
                                                        raw_response=res
                                                    )
                                                except Exception as e:
                                                    logger.debug(f"Ошибка при логировании ответа LLM после tool_calls: {e}")
                                                
                                                # Обновляем res_tool_calls для дальнейшей обработки
                                                res_tool_calls = getattr(res, 'tool_calls', None)
                                                logger.debug(f"После вызова инструмента res.tool_calls: {res_tool_calls}")
                                                
                                                # Проверяем статус ответа
                                                res_is_failed = getattr(res, 'is_failed', False)
                                                if res_is_failed:
                                                    error_msg = f"Run завершился с ошибкой после вызова инструмента из JSON"
                                                    logger.error(f"Ошибка в агенте {self.agent_name}: {error_msg}")
                                                    raise RuntimeError("run is failed and don't have a message result")
                                                
                                                # Продолжаем цикл, чтобы проверить, не появился ли новый JSON с инструментом
                                                # или не появились ли tool_calls
                                                continue
                                            except Exception as e:
                                                # Проверяем, не является ли это CallManagerException
                                                from .tools.call_manager_tools import CallManagerException
                                                if isinstance(e, CallManagerException):
                                                    # Сохраняем результат CallManager и прекращаем работу агента
                                                    self._call_manager_result = e.escalation_result
                                                    logger.info(f"CallManager вызван через JSON (исключение), прекращаем работу агента {self.agent_name}")
                                                    # Выходим из цикла обработки JSON
                                                    break
                                                else:
                                                    logger.error(f"Ошибка при вызове инструмента {tool_name}: {e}")
                                                    # Продолжаем обработку, возможно агент сам обработает ошибку
                                                    break
                                        else:
                                            logger.error(f"Инструмент {tool_name} не найден в списке доступных инструментов")
                                            # Не возвращаем этот JSON, продолжаем обработку
                                            break
                                    else:
                                        # Это не JSON с инструментом, выходим из цикла
                                        break
                                else:
                                    # Это не словарь, выходим из цикла
                                    break
                            except (json.JSONDecodeError, ValueError):
                                # Это не JSON, выходим из цикла и продолжаем нормальную обработку
                                break
                        else:
                            # res.text пустой, выходим из цикла
                            break
                    except Exception as e:
                        logger.debug(f"Ошибка при проверке res.text на JSON: {e}")
                        break
                else:
                    # res_tool_calls не пустой, выходим из цикла обработки JSON
                    # Дальше будет обработан в основном цикле обработки tool_calls
                    break
            
            if json_iteration >= max_json_iterations:
                logger.warning(f"Достигнуто максимальное количество итераций обработки JSON с инструментами: {max_json_iterations}")
            
            # Проверяем, был ли вызван CallManager в блоке обработки JSON
            if self._call_manager_result is not None:
                logger.info(f"CallManager был вызван в блоке обработки JSON, прекращаем работу агента {self.agent_name}")
                return "[CALL_MANAGER_RESULT]"
            
            # Проверяем, не содержит ли res.text маркер [CALL_MANAGER] в начале
            if res_text and res_text.strip().startswith("[CALL_MANAGER]"):
                logger.warning(f"Обнаружен маркер [CALL_MANAGER] в res.text, пытаемся обработать как вызов CallManager")
                # Пытаемся извлечь reason из текста
                reason = "Клиент запросил связь с менеджером"
                try:
                    # Пытаемся найти JSON после [CALL_MANAGER]
                    json_start = res_text.find('{')
                    if json_start >= 0:
                        json_str = res_text[json_start:]
                        parsed = json.loads(json_str)
                        reason = parsed.get('reason', reason)
                except:
                    pass
                
                # Вызываем CallManager напрямую
                if 'CallManager' in self.tools:
                    try:
                        from .tools.call_manager_tools import CallManagerException
                        fn = self.tools['CallManager']
                        obj = fn(reason=reason)
                        tool_result = obj.process(thread) if hasattr(obj, 'process') else str(obj)
                    except CallManagerException as e:
                        self._call_manager_result = e.escalation_result
                        logger.info(f"CallManager вызван через маркер [CALL_MANAGER], прекращаем работу агента {self.agent_name}")
                        return "[CALL_MANAGER_RESULT]"
                    except Exception as e:
                        logger.error(f"Ошибка при обработке маркера [CALL_MANAGER]: {e}")
            
            # Цикл обработки Function Calls - может быть несколько раундов вызовов инструментов
            max_iterations = 10  # Защита от бесконечного цикла
            iteration = 0
            
            while res_tool_calls and iteration < max_iterations:
                # Проверяем, был ли вызван CallManager в предыдущей итерации
                if self._call_manager_result is not None:
                    logger.info(f"CallManager был вызван в цикле обработки tool_calls, прекращаем работу агента {self.agent_name}")
                    return "[CALL_MANAGER_RESULT]"
                
                iteration += 1
                logger.debug(f"Итерация обработки tool_calls: {iteration}")
                
                result = []
                for f in res_tool_calls:
                    logger.debug(f"Вызов функции {f.function.name}", f"args={f.function.arguments}")
                    
                    # Проверяем регистронезависимо, так как SDK может возвращать lowercase
                    tool_name = f.function.name
                    tool_found = None
                    
                    # Сначала пробуем точное совпадение
                    if tool_name in self.tools:
                        tool_found = tool_name
                    else:
                        # Пробуем найти регистронезависимо
                        for key in self.tools.keys():
                            if key.lower() == tool_name.lower():
                                tool_found = key
                                break
                    
                    if tool_found:
                        fn = self.tools[tool_found]
                        # Обрабатываем аргументы (могут быть строкой JSON или словарём)
                        args = f.function.arguments
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                logger.error(f"Не удалось распарсить аргументы функции {f.function.name}")
                                continue
                        
                        try:
                            obj = fn(**args)
                            x = obj.process(thread) if hasattr(obj, 'process') else str(obj)
                            result.append({"name": tool_found, "content": x})
                            
                            # Сохраняем информацию о вызове для отслеживания
                            self._last_tool_calls.append({
                                "name": tool_found,
                                "args": args,
                                "result": x
                            })
                        except Exception as e:
                            # Проверяем, не является ли это CallManagerException
                            from .tools.call_manager_tools import CallManagerException
                            if isinstance(e, CallManagerException):
                                # Сохраняем результат CallManager и прекращаем работу агента
                                self._call_manager_result = e.escalation_result
                                logger.info(f"CallManager вызван через инструмент, прекращаем работу агента {self.agent_name}")
                                # Прерываем цикл обработки tool_calls
                                break
                            else:
                                logger.error(f"Ошибка при выполнении инструмента {f.function.name}: {e}")
                                result.append({
                                    "name": f.function.name,
                                    "content": f"Ошибка при выполнении инструмента: {str(e)}"
                                })
                    else:
                        logger.warning(f"Инструмент {f.function.name} не найден в списке доступных инструментов")
                        result.append({
                            "name": f.function.name,
                            "content": f"Инструмент {f.function.name} недоступен"
                        })
                
                # Проверяем, был ли вызван CallManager
                if self._call_manager_result is not None:
                    # Прекращаем обработку tool_calls и возвращаем результат CallManager
                    logger.info(f"CallManager был вызван, прекращаем обработку tool_calls для агента {self.agent_name}")
                    break
                
                if result:
                    # Логируем результаты инструментов перед отправкой в LLM
                    try:
                        llm_request_logger.log_tool_results_to_llm(
                            agent_name=self.agent_name,
                            tool_results=result
                        )
                    except Exception as e:
                        logger.debug(f"Ошибка при логировании результатов инструментов: {e}")
                    
                    run.submit_tool_results(result)
                    res = run.wait()  # Получаем следующий ответ, который может содержать новые tool_calls
                    
                    # Логируем ответ от LLM после отправки результатов инструментов
                    try:
                        res_text = getattr(res, 'text', None) if res else None
                        res_tool_calls = getattr(res, 'tool_calls', None) if res else None
                        llm_request_logger.log_response_from_llm(
                            agent_name=self.agent_name,
                            response_text=res_text,
                            tool_calls=res_tool_calls if res_tool_calls else None,
                            raw_response=res
                        )
                    except Exception as e:
                        logger.debug(f"Ошибка при логировании ответа LLM после tool_calls: {e}")
                    
                    # Детальное логирование результата в цикле
                    logger.debug(f"Результат run.wait() в цикле (итерация {iteration}):")
                    logger.debug(f"  - Тип res: {type(res)}")
                    logger.debug(f"  - res is None: {res is None}")
                    
                    if res is None:
                        error_msg = "Run завершился без результата во время обработки tool_calls (res is None)"
                        logger.error(f"Ошибка в агенте {self.agent_name}: {error_msg}")
                        logger.error(f"Детали: run_id={getattr(run, 'id', 'N/A')}, итерация={iteration}, tool_calls={len(result)}")
                        raise RuntimeError("run is failed and don't have a message result")
                    
                    # Проверяем статус через безопасные атрибуты
                    res_is_failed = getattr(res, 'is_failed', False)
                    res_status = getattr(res, 'status', None)
                    res_error = getattr(res, 'error', None)
                    
                    logger.debug(f"  - res.is_failed: {res_is_failed}, res.status: {res_status}")
                    if res_error:
                        logger.debug(f"  - res.error: {res_error}")
                    
                    # Проверяем результат после каждого wait() в цикле
                    if res_is_failed:
                        error_msg = f"Run завершился с ошибкой во время обработки tool_calls (is_failed=True, status={res_status})"
                        logger.error(f"Ошибка в агенте {self.agent_name}: {error_msg}")
                        logger.error(f"Детали: run_id={getattr(run, 'id', 'N/A')}, итерация={iteration}, tool_calls={len(result)}")
                        if res_error:
                            logger.error(f"Ошибка run: {res_error}")
                        # Создаем исключение с информацией об ошибке для проверки типа
                        runtime_error = RuntimeError("run is failed and don't have a message result")
                        runtime_error.res_error = res_error  # Сохраняем res_error для проверки
                        raise runtime_error
                    
                    # Безопасно получаем tool_calls для следующей итерации
                    res_tool_calls = getattr(res, 'tool_calls', None)
                else:
                    # Если нет результатов для отправки, прерываем цикл
                    break
            
            if iteration >= max_iterations:
                logger.warning(f"Достигнуто максимальное количество итераций обработки tool_calls: {max_iterations}")
            
            # Проверяем, был ли вызван CallManager
            if self._call_manager_result is not None:
                # Возвращаем специальный маркер вместо текста ответа
                logger.info(f"Возвращаем результат CallManager для агента {self.agent_name}")
                return "[CALL_MANAGER_RESULT]"
            
            # Проверяем наличие текста перед возвратом
            logger.debug(f"Финальная проверка результата для агента {self.agent_name}:")
            logger.debug(f"  - res is None: {res is None}")
            
            if res is None:
                error_msg = "Run завершился без результата (res is None)"
                logger.error(f"Ошибка в агенте {self.agent_name}: {error_msg}")
                logger.error(f"Детали: run_id={getattr(run, 'id', 'N/A')}, message={message[:200]}, итераций={iteration}")
                raise RuntimeError("run is failed and don't have a message result")
            
            # Финальная проверка статуса
            res_is_failed = getattr(res, 'is_failed', False)
            res_status = getattr(res, 'status', None)
            res_error = getattr(res, 'error', None)
            
            logger.debug(f"  - res.is_failed: {res_is_failed}, res.status: {res_status}")
            
            if res_is_failed:
                error_msg = f"Run завершился с ошибкой перед возвратом (is_failed=True, status={res_status})"
                logger.error(f"Ошибка в агенте {self.agent_name}: {error_msg}")
                logger.error(f"Детали: run_id={getattr(run, 'id', 'N/A')}, message={message[:200]}, итераций={iteration}")
                if res_error:
                    logger.error(f"Ошибка run: {res_error}")
                # Создаем исключение с информацией об ошибке для проверки типа
                runtime_error = RuntimeError("run is failed and don't have a message result")
                runtime_error.res_error = res_error  # Сохраняем res_error для проверки
                raise runtime_error
            
            # Безопасно получаем text через try-except
            try:
                res_text = res.text
                if res_text is None:
                    error_msg = "Run завершился без результата сообщения (res.text is None)"
                    logger.error(f"Ошибка в агенте {self.agent_name}: {error_msg}")
                    logger.error(f"Детали: run_id={getattr(run, 'id', 'N/A')}, is_failed={res_is_failed}, status={res_status}")
                    raise RuntimeError("run is failed and don't have a message result")
                
                logger.debug(f"  - res.text значение: {repr(res_text[:200]) if res_text else 'None/Empty'}")
                logger.debug(f"Успешно получен ответ от агента {self.agent_name}, длина текста: {len(res_text)}")
                
                # Сохраняем результаты инструментов в историю после успешного выполнения агента
                try:
                    chat_id = getattr(thread, 'chat_id', None)
                    if chat_id and self._last_tool_calls:
                        tool_history_service = get_tool_history_service()
                        tool_history_service.save_tool_results(
                            chat_id=chat_id,
                            tool_results=self._last_tool_calls,
                            cycle_metadata={
                                "agent_name": self.agent_name,
                                "timestamp": datetime.now().isoformat()
                            }
                        )
                        logger.debug(f"Сохранены результаты инструментов в историю для chat_id={chat_id}, инструментов: {len(self._last_tool_calls)}")
                except Exception as e:
                    logger.debug(f"Ошибка при сохранении результатов инструментов в историю: {e}")
                
                return res_text
            except (ValueError, AttributeError) as e:
                error_msg = f"Не удалось получить res.text: {e}"
                logger.error(f"Ошибка в агенте {self.agent_name}: {error_msg}")
                logger.error(f"Детали: run_id={getattr(run, 'id', 'N/A')}, is_failed={res_is_failed}, status={res_status}")
                logger.error(f"Доступные атрибуты res: {[attr for attr in dir(res) if not attr.startswith('_')]}")
                logger.error(f"Сообщение агента: {message[:200]}")
                raise RuntimeError("run is failed and don't have a message result")
        
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            
            # Логируем ошибку в LLM лог
            try:
                llm_request_logger.log_error(
                    agent_name=self.agent_name,
                    error=e,
                    context=f"Message: {message[:200]}"
                )
            except Exception as log_error:
                logger.debug(f"Ошибка при логировании ошибки: {log_error}")
            
            logger.error(f"Ошибка в агенте {self.agent_name}: {e}")
            logger.error(f"Тип ошибки: {type(e).__name__}")
            logger.error(f"Сообщение агента: {message[:200]}")
            logger.error(f"Thread ID: {thread.id if hasattr(thread, 'id') else 'N/A'}")
            logger.error(f"Traceback:\n{error_traceback}")
            raise

