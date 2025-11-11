"""
Базовый класс для агентов
"""
import json
from typing import Optional, Dict, Any
from yandex_cloud_ml_sdk._threads.thread import Thread
from yandex_cloud_ml_sdk._assistants.assistant import Assistant
from ..services.langgraph_service import LangGraphService
from ..services.logger_service import logger
from ..services.error_checker import ErrorChecker
from ..services.call_manager_service import CallManagerService
from ..services.llm_logger import llm_logger


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
        else:
            # Создаём инструменты
            tool_list = []
            if tools:
                self.tools = {x.__name__: x for x in tools}
                tool_list = [langgraph_service.sdk.tools.function(x) for x in tools]
            else:
                self.tools = {}
            
            # Создаём Assistant с именем (или используем существующего)
            self.assistant = langgraph_service.get_or_create_assistant(
                instruction=instruction,
                tools=tool_list,
                name=self.agent_name
            )
        
        # Инициализируем список для отслеживания tool_calls
        self._last_tool_calls = []
    
    def __call__(self, message: str, thread: Thread) -> str:
        """
        Выполнение запроса к агенту с retry логикой для InternalServerError
        
        :param message: Сообщение для агента
        :param thread: Thread для выполнения запроса
        :return: Ответ агента
        """
        max_retries = 3
        last_error = None
        last_error_message = None
        message_added = False  # Флаг для отслеживания добавления сообщения в thread
        
        for attempt in range(1, max_retries + 1):
            try:
                return self._execute_request(message, thread, message_added)
            except RuntimeError as e:
                error_message = str(e)
                # Получаем информацию об ошибке из res.error если доступна
                res_error = getattr(e, 'res_error', None) if hasattr(e, 'res_error') else None
                error_to_check = res_error if res_error else error_message
                
                # Проверяем, является ли это InternalServerError
                if ErrorChecker.is_internal_server_error(error_to_check):
                    last_error = e
                    last_error_message = error_to_check
                    message_added = True  # Сообщение уже было добавлено при первой попытке
                    logger.warning(
                        f"Попытка {attempt}/{max_retries} для агента {self.agent_name}: "
                        f"InternalServerError - повторяем запрос"
                    )
                    if attempt < max_retries:
                        continue
                    else:
                        # После 3 неудачных попыток вызываем CallManager
                        logger.error(
                            f"Агент {self.agent_name}: все {max_retries} попытки завершились "
                            f"InternalServerError. Вызываем CallManager."
                        )
                        CallManagerService.handle_critical_error(
                            error_message=last_error_message or error_message,
                            agent_name=self.agent_name,
                            message=message,
                            thread_id=getattr(thread, 'id', None)
                        )
                        # После вызова CallManager все равно выбрасываем исключение
                        raise
                else:
                    # Если это не InternalServerError, сразу выбрасываем исключение
                    raise
            except Exception as e:
                # Для других типов ошибок не делаем retry
                raise
    
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
                # Логируем сообщение пользователя ПЕРЕД добавлением в thread
                thread_id = getattr(thread, 'id', None)
                llm_logger.log_user_message(message, thread_id)
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
            tools = getattr(self, 'tools', {})
            tool_list = list(tools.values()) if tools else []
            
            # Логируем запуск ассистента
            thread_id = getattr(thread, 'id', None)
            llm_logger.log_assistant_run_start(
                agent_name=self.agent_name,
                thread_id=thread_id,
                instruction=instruction,
                tools=tool_list,
                thread_messages=thread_messages,
                assistant_obj=self.assistant,
                thread_obj=thread
            )
            
            # Запускаем Assistant
            run = self.assistant.run(thread)
            logger.debug(f"Запущен run для агента {self.agent_name}, run_id: {run.id if hasattr(run, 'id') else 'N/A'}")
            
            res = run.wait()
            
            # Логируем ответ от LLM
            try:
                res_text = getattr(res, 'text', None) if res else None
                res_tool_calls = getattr(res, 'tool_calls', None) if res else None
                llm_logger.log_llm_response(
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
            
            # Проверяем, не является ли res.text JSON-описанием инструмента
            # Если да, то это промежуточная стадия и нужно продолжить обработку
            if res_tool_calls is None or (isinstance(res_tool_calls, list) and len(res_tool_calls) == 0):
                try:
                    res_text_check = res.text
                    if res_text_check:
                        # Проверяем, не является ли это JSON с описанием инструмента
                        try:
                            parsed_json = json.loads(res_text_check)
                            if isinstance(parsed_json, dict) and 'tool' in parsed_json:
                                tool_name = parsed_json.get('tool')
                                tool_args = parsed_json.get('arguments', {})
                                
                                logger.warning(f"Обнаружен JSON с инструментом в res.text, но res.tool_calls пустой.")
                                logger.warning(f"Инструмент: {tool_name}, аргументы: {tool_args}")
                                
                                # Если инструмент есть в списке доступных, вызываем его вручную
                                if tool_name in self.tools:
                                    logger.info(f"Вызываем инструмент {tool_name} вручную из JSON")
                                    fn = self.tools[tool_name]
                                    try:
                                        obj = fn(**tool_args)
                                        tool_result = obj.process(thread) if hasattr(obj, 'process') else str(obj)
                                        
                                        # Сохраняем информацию о вызове
                                        self._last_tool_calls.append({
                                            "name": tool_name,
                                            "args": tool_args,
                                            "result": tool_result
                                        })
                                        
                                        # Логируем результаты инструментов перед отправкой в LLM
                                        tool_result_data = [{"name": tool_name, "content": tool_result}]
                                        try:
                                            llm_logger.log_tool_results(
                                                agent_name=self.agent_name,
                                                tool_results=tool_result_data
                                            )
                                        except Exception as e:
                                            logger.debug(f"Ошибка при логировании результатов инструментов: {e}")
                                        
                                        # Отправляем результат обратно в run
                                        run.submit_tool_results(tool_result_data)
                                        
                                        # Получаем следующий ответ от агента
                                        res = run.wait()
                                        
                                        # Логируем ответ от LLM после отправки результатов инструментов
                                        try:
                                            res_text = getattr(res, 'text', None) if res else None
                                            res_tool_calls = getattr(res, 'tool_calls', None) if res else None
                                            llm_logger.log_llm_response(
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
                                        
                                        # Проверяем, что res.text теперь содержит нормальный ответ, а не JSON
                                        try:
                                            new_res_text = getattr(res, 'text', None) if res else None
                                            if new_res_text:
                                                # Проверяем, не является ли ответ все еще JSON с инструментом
                                                try:
                                                    parsed_check = json.loads(new_res_text)
                                                    if isinstance(parsed_check, dict) and 'tool' in parsed_check:
                                                        logger.warning(f"После вызова инструмента res.text все еще содержит JSON с инструментом. Делаем еще один wait()...")
                                                        # Делаем еще один wait() чтобы получить финальный ответ
                                                        res = run.wait()
                                                        res_tool_calls = getattr(res, 'tool_calls', None)
                                                        logger.debug(f"После дополнительного wait() res.tool_calls: {res_tool_calls}")
                                                except (json.JSONDecodeError, ValueError):
                                                    # Это нормальный ответ, не JSON - все хорошо
                                                    pass
                                        except Exception as e:
                                            logger.debug(f"Ошибка при проверке res.text после вызова инструмента: {e}")
                                    except Exception as e:
                                        logger.error(f"Ошибка при вызове инструмента {tool_name}: {e}")
                                        # Продолжаем обработку, возможно агент сам обработает ошибку
                                else:
                                    logger.error(f"Инструмент {tool_name} не найден в списке доступных инструментов")
                                    # Не возвращаем этот JSON, продолжаем обработку
                                    # Попробуем получить tool_calls из других источников или продолжить run
                                    logger.debug("Попытка продолжить run для получения финального ответа...")
                                    res = run.wait()
                                    res_tool_calls = getattr(res, 'tool_calls', None)
                                    logger.debug(f"После повторного wait() res.tool_calls: {res_tool_calls}")
                        except (json.JSONDecodeError, ValueError):
                            # Это не JSON, продолжаем нормальную обработку
                            pass
                except Exception as e:
                    logger.debug(f"Ошибка при проверке res.text на JSON: {e}")
            
            # Цикл обработки Function Calls - может быть несколько раундов вызовов инструментов
            max_iterations = 10  # Защита от бесконечного цикла
            iteration = 0
            
            while res_tool_calls and iteration < max_iterations:
                iteration += 1
                logger.debug(f"Итерация обработки tool_calls: {iteration}")
                
                result = []
                for f in res_tool_calls:
                    logger.debug(f"Вызов функции {f.function.name}", f"args={f.function.arguments}")
                    
                    if f.function.name in self.tools:
                        fn = self.tools[f.function.name]
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
                            result.append({"name": f.function.name, "content": x})
                            
                            # Сохраняем информацию о вызове для отслеживания
                            self._last_tool_calls.append({
                                "name": f.function.name,
                                "args": args,
                                "result": x
                            })
                        except Exception as e:
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
                
                if result:
                    # Логируем результаты инструментов перед отправкой в LLM
                    try:
                        llm_logger.log_tool_results(
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
                        llm_logger.log_llm_response(
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
                llm_logger.log_error(
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

