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
        assistant: Optional[Assistant] = None
    ):
        self.langgraph_service = langgraph_service
        self.instruction = instruction
        
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
            
            # Создаём Assistant
            self.assistant = langgraph_service.create_assistant(
                instruction=instruction,
                tools=tool_list
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
            res = run.wait()
            
            # Обрабатываем Function Calls
            if res.tool_calls:
                result = []
                for f in res.tool_calls:
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
                        
                        obj = fn(**args)
                        x = obj.process(thread) if hasattr(obj, 'process') else str(obj)
                        result.append({"name": f.function.name, "content": x})
                        
                        # Сохраняем информацию о вызове для отслеживания
                        self._last_tool_calls.append({
                            "name": f.function.name,
                            "args": args,
                            "result": x
                        })
                
                if result:
                    run.submit_tool_results(result)
                    res = run.wait()
            
            return res.text
        
        except Exception as e:
            logger.error(f"Ошибка в агенте: {e}")
            raise

