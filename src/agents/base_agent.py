"""
Базовый класс для агентов
"""
import json
from typing import Optional, Dict, Any
from yandex_cloud_ml_sdk._threads.thread import Thread
from yandex_cloud_ml_sdk._assistants.assistant import Assistant
from ..services.langgraph_service import LangGraphService
from ..services.logger_service import logger


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
        """Выполнение запроса к агенту"""
        try:
            # Очищаем предыдущие tool_calls
            self._last_tool_calls = []
            
            # Добавляем сообщение в Thread
            thread.write(message)
            
            # Запускаем Assistant
            run = self.assistant.run(thread)
            logger.debug(f"Запущен run для агента {self.agent_name}, run_id: {run.id if hasattr(run, 'id') else 'N/A'}")
            
            res = run.wait()
            
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
                raise RuntimeError("run is failed and don't have a message result")
            
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
            if res_tool_calls:
                logger.debug(f"  - res.tool_calls: {res_tool_calls}")
            
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
                    run.submit_tool_results(result)
                    res = run.wait()  # Получаем следующий ответ, который может содержать новые tool_calls
                    
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
                        raise RuntimeError("run is failed and don't have a message result")
                    
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
                raise RuntimeError("run is failed and don't have a message result")
            
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
            logger.error(f"Ошибка в агенте {self.agent_name}: {e}")
            logger.error(f"Тип ошибки: {type(e).__name__}")
            logger.error(f"Сообщение агента: {message[:200]}")
            logger.error(f"Thread ID: {thread.id if hasattr(thread, 'id') else 'N/A'}")
            logger.error(f"Traceback:\n{error_traceback}")
            raise

