"""
Система логирования запросов и ответов LLM в сыром виде
"""
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from threading import Lock


class LLMLogger:
    """Логгер для записи всех запросов и ответов LLM в сыром виде"""
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Создаём папку для логов
        self.logs_dir = Path("logs")
        self.logs_dir.mkdir(exist_ok=True)
        
        # Файл для текущего запроса
        self.current_log_file: Optional[Path] = None
        self.request_start_time: Optional[datetime] = None
        self._file_lock = Lock()
        self._request_counter = 0
        
        self._initialized = True
    
    def start_new_request(self) -> Path:
        """Начать новый запрос - создать новый файл лога"""
        with self._file_lock:
            # Закрываем предыдущий файл если был
            if self.current_log_file:
                try:
                    # Добавляем завершающую строку
                    with open(self.current_log_file, 'a', encoding='utf-8') as f:
                        f.write(f"\n{'='*80}\n")
                        f.write(f"REQUEST COMPLETED\n")
                        f.write(f"{'='*80}\n")
                except:
                    pass
            
            # Создаём новый файл для текущего запроса
            self._request_counter += 1
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # Добавляем миллисекунды для уникальности
            self.current_log_file = self.logs_dir / f"llm_request_{timestamp}.log"
            self.request_start_time = datetime.now()
            
            # Записываем заголовок запроса
            try:
                with open(self.current_log_file, 'w', encoding='utf-8') as f:
                    f.write(f"{'='*80}\n")
                    f.write(f"NEW REQUEST STARTED\n")
                    f.write(f"{'='*80}\n")
                    f.write(f"Request ID: {self._request_counter}\n")
                    f.write(f"Start Time: {self.request_start_time.isoformat()}\n")
                    f.write(f"Log File: {self.current_log_file.name}\n")
                    f.write(f"{'='*80}\n\n")
            except Exception as e:
                print(f"Ошибка создания файла лога: {e}")
            
            return self.current_log_file
    
    def _get_log_file(self) -> Path:
        """Получить файл лога для текущего запроса"""
        if self.current_log_file is None:
            # Если файл не создан, создаём его
            return self.start_new_request()
        return self.current_log_file
    
    def _write_raw(self, data: str):
        """Записать сырые данные в файл"""
        log_file = self._get_log_file()
        
        with self._file_lock:
            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(data)
                    f.write('\n')
                    f.flush()
            except Exception as e:
                print(f"Ошибка записи в лог: {e}")
    
    def log_user_message(self, message: str, thread_id: Optional[str] = None):
        """Логировать сообщение пользователя (то, что будет отправлено в LLM через thread.write)"""
        timestamp = datetime.now().isoformat()
        log_entry = f"\n{'='*80}\n"
        log_entry += f"[{timestamp}] USER MESSAGE (RAW - sent to LLM via thread.write)\n"
        log_entry += f"{'='*80}\n"
        if thread_id:
            log_entry += f"Thread ID: {thread_id}\n"
        log_entry += f"Message (exact text sent to LLM):\n{message}\n"
        self._write_raw(log_entry)
    
    def log_assistant_run_start(
        self,
        agent_name: str,
        thread_id: Optional[str] = None,
        instruction: Optional[str] = None,
        tools: Optional[List[Any]] = None,
        thread_messages: Optional[List[Any]] = None,
        assistant_obj: Optional[Any] = None,
        thread_obj: Optional[Any] = None
    ):
        """Логировать начало запуска ассистента - это то, что реально отправляется в LLM через assistant.run(thread)"""
        timestamp = datetime.now().isoformat()
        log_entry = f"\n{'='*80}\n"
        log_entry += f"[{timestamp}] ASSISTANT RUN START (RAW - what is sent to LLM via assistant.run)\n"
        log_entry += f"{'='*80}\n"
        log_entry += f"Agent: {agent_name}\n"
        if thread_id:
            log_entry += f"Thread ID: {thread_id}\n"
        
        log_entry += f"\n--- FULL CONTEXT SENT TO LLM ---\n"
        log_entry += f"This includes: instruction, tools, and ALL thread messages (full conversation history)\n"
        
        if instruction:
            log_entry += f"\n--- INSTRUCTION (RAW - sent to LLM) ---\n{instruction}\n"
        
        if tools:
            log_entry += f"\n--- TOOLS (RAW) ---\n"
            try:
                # Пытаемся получить информацию о инструментах в сыром виде
                tools_info = []
                for tool in tools:
                    if hasattr(tool, '__dict__'):
                        # Пытаемся сериализовать в JSON для более сырого вида
                        try:
                            tools_info.append(json.dumps(tool.__dict__, ensure_ascii=False, indent=2, default=str))
                        except:
                            tools_info.append(str(tool.__dict__))
                    else:
                        tools_info.append(str(tool))
                log_entry += "\n".join(tools_info) + "\n"
            except Exception as e:
                log_entry += f"Error serializing tools: {e}\n"
        
        if thread_messages:
            log_entry += f"\n--- THREAD MESSAGES (RAW - ALL messages sent to LLM, including full conversation history) ---\n"
            log_entry += f"Total messages in thread: {len(thread_messages)}\n"
            try:
                for i, msg in enumerate(thread_messages):
                    if hasattr(msg, 'author') and hasattr(msg, 'text'):
                        role = getattr(msg.author, 'role', 'UNKNOWN')
                        text = getattr(msg, 'text', '')
                        # Пытаемся получить все атрибуты сообщения
                        msg_attrs = {}
                        if hasattr(msg, '__dict__'):
                            try:
                                msg_attrs = {k: str(v) for k, v in msg.__dict__.items() if not k.startswith('_')}
                            except:
                                pass
                        log_entry += f"\nMessage {i} (sent to LLM):\n"
                        log_entry += f"  Role: {role}\n"
                        log_entry += f"  Text (exact): {text}\n"
                        if msg_attrs:
                            log_entry += f"  All attributes: {json.dumps(msg_attrs, ensure_ascii=False, indent=2, default=str)}\n"
                    else:
                        log_entry += f"\nMessage {i} (raw object sent to LLM): {str(msg)}\n"
            except Exception as e:
                log_entry += f"Error serializing thread messages: {e}\n"
        
        # Логируем сырые объекты assistant и thread если доступны
        if assistant_obj:
            log_entry += f"\n--- ASSISTANT OBJECT (RAW) ---\n"
            try:
                if hasattr(assistant_obj, '__dict__'):
                    assistant_dict = {k: str(v) for k, v in assistant_obj.__dict__.items() if not k.startswith('_')}
                    log_entry += json.dumps(assistant_dict, ensure_ascii=False, indent=2, default=str) + "\n"
                else:
                    log_entry += str(assistant_obj) + "\n"
            except Exception as e:
                log_entry += f"Error serializing assistant object: {e}\n"
        
        if thread_obj:
            log_entry += f"\n--- THREAD OBJECT (RAW) ---\n"
            try:
                if hasattr(thread_obj, '__dict__'):
                    thread_dict = {k: str(v) for k, v in thread_obj.__dict__.items() if not k.startswith('_')}
                    log_entry += json.dumps(thread_dict, ensure_ascii=False, indent=2, default=str) + "\n"
                else:
                    log_entry += str(thread_obj) + "\n"
            except Exception as e:
                log_entry += f"Error serializing thread object: {e}\n"
        
        self._write_raw(log_entry)
    
    def log_llm_response(
        self,
        agent_name: str,
        response_text: Optional[str] = None,
        tool_calls: Optional[List[Any]] = None,
        raw_response: Optional[Any] = None
    ):
        """Логировать ответ от LLM"""
        timestamp = datetime.now().isoformat()
        log_entry = f"\n{'='*80}\n"
        log_entry += f"[{timestamp}] LLM RESPONSE (RAW)\n"
        log_entry += f"{'='*80}\n"
        log_entry += f"Agent: {agent_name}\n"
        
        if response_text is not None:
            log_entry += f"\n--- RESPONSE TEXT (RAW) ---\n{response_text}\n"
        
        if tool_calls:
            log_entry += f"\n--- TOOL CALLS (RAW) ---\n"
            try:
                for i, tool_call in enumerate(tool_calls):
                    log_entry += f"Tool Call {i}:\n"
                    if hasattr(tool_call, 'function'):
                        func_name = getattr(tool_call.function, 'name', 'UNKNOWN')
                        func_args = getattr(tool_call.function, 'arguments', {})
                        log_entry += f"  Function Name: {func_name}\n"
                        if isinstance(func_args, str):
                            log_entry += f"  Arguments (raw string): {func_args}\n"
                        else:
                            log_entry += f"  Arguments (raw): {json.dumps(func_args, ensure_ascii=False, indent=2)}\n"
                        
                        # Пытаемся получить все атрибуты function объекта
                        if hasattr(tool_call.function, '__dict__'):
                            try:
                                func_dict = {k: str(v) for k, v in tool_call.function.__dict__.items()}
                                log_entry += f"  Function Object: {json.dumps(func_dict, ensure_ascii=False, indent=2, default=str)}\n"
                            except:
                                pass
                    
                    # Пытаемся получить все атрибуты tool_call объекта
                    if hasattr(tool_call, '__dict__'):
                        try:
                            tool_call_dict = {k: str(v) for k, v in tool_call.__dict__.items() if not k.startswith('_')}
                            log_entry += f"  Tool Call Object: {json.dumps(tool_call_dict, ensure_ascii=False, indent=2, default=str)}\n"
                        except:
                            pass
                    
                    if not hasattr(tool_call, 'function'):
                        log_entry += f"  Raw: {str(tool_call)}\n"
            except Exception as e:
                log_entry += f"Error serializing tool_calls: {e}\n"
                log_entry += f"Raw tool_calls: {str(tool_calls)}\n"
        
        if raw_response is not None:
            log_entry += f"\n--- RAW RESPONSE OBJECT (ALL ATTRIBUTES) ---\n"
            try:
                # Пытаемся получить все атрибуты объекта ответа
                if hasattr(raw_response, '__dict__'):
                    response_dict = {}
                    for k, v in raw_response.__dict__.items():
                        try:
                            response_dict[k] = str(v)
                        except:
                            response_dict[k] = "<unserializable>"
                    log_entry += json.dumps(response_dict, ensure_ascii=False, indent=2, default=str) + "\n"
                else:
                    log_entry += str(raw_response) + "\n"
                
                # Пытаемся получить все публичные атрибуты через dir()
                try:
                    public_attrs = [attr for attr in dir(raw_response) if not attr.startswith('_')]
                    log_entry += f"\nPublic attributes: {', '.join(public_attrs)}\n"
                    for attr in public_attrs:
                        try:
                            value = getattr(raw_response, attr)
                            if not callable(value):
                                log_entry += f"  {attr}: {str(value)[:200]}\n"
                        except:
                            pass
                except:
                    pass
            except Exception as e:
                log_entry += f"Error serializing raw response: {e}\n"
        
        self._write_raw(log_entry)
    
    def log_tool_results(
        self,
        agent_name: str,
        tool_results: List[Dict[str, Any]]
    ):
        """Логировать результаты инструментов, отправляемые обратно в LLM"""
        timestamp = datetime.now().isoformat()
        log_entry = f"\n{'='*80}\n"
        log_entry += f"[{timestamp}] TOOL RESULTS (RAW - sent to LLM)\n"
        log_entry += f"{'='*80}\n"
        log_entry += f"Agent: {agent_name}\n"
        log_entry += f"\n--- TOOL RESULTS (RAW JSON) ---\n"
        
        try:
            # Логируем как сырой JSON
            log_entry += json.dumps(tool_results, ensure_ascii=False, indent=2, default=str) + "\n"
            log_entry += f"\n--- TOOL RESULTS (FORMATTED) ---\n"
            for i, result in enumerate(tool_results):
                tool_name = result.get('name', 'UNKNOWN')
                tool_content = result.get('content', '')
                log_entry += f"Tool {i}: {tool_name}\n"
                log_entry += f"Result (raw): {tool_content}\n"
                log_entry += f"{'-'*40}\n"
        except Exception as e:
            log_entry += f"Error serializing tool results: {e}\n"
            log_entry += f"Raw tool_results: {str(tool_results)}\n"
        
        self._write_raw(log_entry)
    
    def log_error(self, agent_name: str, error: Exception, context: Optional[str] = None):
        """Логировать ошибку"""
        timestamp = datetime.now().isoformat()
        log_entry = f"\n{'='*80}\n"
        log_entry += f"[{timestamp}] ERROR\n"
        log_entry += f"{'='*80}\n"
        log_entry += f"Agent: {agent_name}\n"
        if context:
            log_entry += f"Context: {context}\n"
        log_entry += f"Error Type: {type(error).__name__}\n"
        log_entry += f"Error Message: {str(error)}\n"
        import traceback
        log_entry += f"\n--- TRACEBACK ---\n{traceback.format_exc()}\n"
        self._write_raw(log_entry)
    
    def start_new_session(self):
        """Начать новую сессию логирования (устаревший метод, используйте start_new_request)"""
        # Закрываем текущий файл если был
        if self.current_log_file:
            try:
                with open(self.current_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n{'='*80}\n")
                    f.write(f"SESSION ENDED\n")
                    f.write(f"{'='*80}\n")
            except:
                pass
        self.current_log_file = None
        self.request_start_time = None


# Глобальный экземпляр логгера
llm_logger = LLMLogger()

