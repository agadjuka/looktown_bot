# План интеграции LangGraph системы в Looktown Bot

## Текущая архитектура

### Что уже есть:
1. **Telegram бот** (`bot.py`, `main.py`) - получает сообщения от пользователей
2. **YandexAgentService** - работает с Responses API через `previous_response_id` для сохранения контекста
3. **YDB** - хранит маппинг `chat_id -> last_response_id`
4. **Сервисы**: AuthService, DebugService, EscalationService
5. **Один агент** - работает через `YC_AGENT_ID` с промптом

### Ограничения текущей системы:
- Использует Responses API (старый подход)
- Контекст хранится через `previous_response_id` (ограниченная история)
- Один агент для всех задач
- Нет маршрутизации по стадиям диалога
- Нет специализированных агентов

---

## Целевая архитектура с LangGraph

### Что нужно реализовать:
1. **Агент определения стадии** - анализирует запрос и определяет стадию диалога
2. **Специализированные агенты**:
   - Агент приветствия
   - Агент бронирования
   - Агент отмены записи
   - Агент переноса записи
3. **LangGraph граф** - координирует работу агентов
4. **Thread вместо previous_response_id** - единая история для всех агентов
5. **Инструменты (Function Calling)** - для работы с системой бронирования

---

## Этап 1: Подготовка инфраструктуры

### 1.1. Установка зависимостей

**Файл: `requirements.txt`**

Добавить:
```python
yandex-cloud-ml-sdk>=1.0.0  # Для работы с Assistant API и Thread
langgraph>=0.2.0            # Для создания графа состояний
pydantic>=2.0.0             # Для структурного вывода и Function Calling
```

### 1.2. Обновление YDB схемы

**Файл: `src/ydb_client.py`**

Добавить методы для работы с Thread ID:
```python
def get_thread_id(self, chat_id: str) -> Optional[str]:
    """Получение thread_id по chat_id"""
    query = """
    DECLARE $id AS String; 
    SELECT thread_id FROM chat_threads WHERE chat_id = $id;
    """
    result = self._execute_query(query, {"$id": chat_id})
    rows = result[0].rows
    return rows[0].thread_id.decode() if rows and rows[0].thread_id else None

def save_thread_id(self, chat_id: str, thread_id: str):
    """Сохранение маппинга chat_id -> thread_id"""
    query = """
    DECLARE $cid AS String; 
    DECLARE $tid AS String;
    UPSERT INTO chat_threads (chat_id, thread_id, updated_at)
    VALUES ($cid, $tid, CurrentUtcTimestamp());
    """
    self._execute_query(query, {
        "$cid": chat_id, 
        "$tid": thread_id
    })

def reset_thread(self, chat_id: str):
    """Сброс thread для чата"""
    query = """
    DECLARE $cid AS String;
    UPDATE chat_threads SET thread_id = NULL, updated_at = CurrentUtcTimestamp()
    WHERE chat_id = $cid;
    """
    self._execute_query(query, {"$cid": chat_id})
```

**Обновить схему таблицы:**
- Добавить поле `thread_id` в таблицу `chat_threads`
- Сохранять и `last_response_id` (для обратной совместимости), и `thread_id`

---

## Этап 2: Создание базовых компонентов

### 2.1. Сервис для работы с Yandex Cloud ML SDK

**Файл: `src/services/langgraph_service.py`** (новый)

```python
"""
Сервис для работы с LangGraph и Assistant API
"""
import os
from typing import Optional
from yandex_cloud_ml_sdk import YCloudML
from yandex_cloud_ml_sdk._threads.thread import Thread
from .logger_service import logger

class LangGraphService:
    """Сервис для работы с LangGraph и Assistant API"""
    
    def __init__(self):
        folder_id = os.getenv("YANDEX_FOLDER_ID")
        api_key = os.getenv("YANDEX_API_KEY_SECRET")
        
        if not folder_id or not api_key:
            raise ValueError("Не заданы YANDEX_FOLDER_ID или YANDEX_API_KEY_SECRET")
        
        self.sdk = YCloudML(folder_id=folder_id, auth=api_key)
        self.model = self.sdk.models.completions("yandexgpt", model_version="rc")
    
    def create_thread(self, ttl_days: int = 30) -> Thread:
        """Создание нового Thread"""
        return self.sdk.threads.create(
            ttl_days=ttl_days,
            expiration_policy="since_last_active"
        )
    
    def get_thread_by_id(self, thread_id: str) -> Optional[Thread]:
        """Получение Thread по ID"""
        try:
            return self.sdk.threads.get(thread_id)
        except Exception as e:
            logger.error(f"Ошибка получения Thread: {e}")
            return None
    
    def create_assistant(self, instruction: str, tools: list = None):
        """Создание Assistant с инструкцией и инструментами"""
        kwargs = {}
        if tools and len(tools) > 0:
            kwargs = {"tools": tools}
        
        assistant = self.sdk.assistants.create(
            self.model,
            ttl_days=30,
            expiration_policy="since_last_active",
            **kwargs
        )
        
        if instruction:
            assistant.update(instruction=instruction)
        
        return assistant
```

### 2.2. Класс Agent (базовый)

**Файл: `src/agents/base_agent.py`** (новый)

```python
"""
Базовый класс для агентов
"""
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
    
    def __call__(self, message: str, thread: Thread) -> str:
        """Выполнение запроса к агенту"""
        try:
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
                        obj = fn(**f.function.arguments)
                        x = obj.process(thread) if hasattr(obj, 'process') else str(obj)
                        result.append({"name": f.function.name, "content": x})
                
                if result:
                    run.submit_tool_results(result)
                    res = run.wait()
            
            return res.text
        
        except Exception as e:
            logger.error(f"Ошибка в агенте: {e}")
            raise
```

---

## Этап 3: Определение стадий и создание агента-роутера

### 3.1. Определение стадий диалога

**Файл: `src/agents/dialogue_stages.py`** (новый)

```python
"""
Определение стадий диалога
"""
from enum import Enum

class DialogueStage(str, Enum):
    """Стадии диалога"""
    GREETING = "greeting"              # Приветствие
    BOOKING = "booking"                # Бронирование
    CANCEL_BOOKING = "cancel_booking"  # Отмена записи
    RESCHEDULE = "reschedule"           # Перенос записи
    GENERAL_QUESTION = "general"        # Общий вопрос
    UNKNOWN = "unknown"                 # Неопределённая стадия
```

### 3.2. Агент определения стадии

**Файл: `src/agents/stage_detector_agent.py`** (новый)

```python
"""
Агент для определения стадии диалога
"""
from pydantic import BaseModel, Field
from typing import Optional
from .base_agent import BaseAgent
from .dialogue_stages import DialogueStage
from ..services.langgraph_service import LangGraphService

class StageDetection(BaseModel):
    """Структура для определения стадии"""
    stage: str = Field(description="Стадия диалога: greeting, booking, cancel_booking, reschedule, general, unknown")
    confidence: float = Field(description="Уверенность в определении стадии (0.0-1.0)", default=0.5)
    extracted_info: Optional[dict] = Field(description="Извлечённая информация из запроса", default=None)

class StageDetectorAgent(BaseAgent):
    """Агент для определения стадии диалога"""
    
    def __init__(self, langgraph_service: LangGraphService):
        instruction = """
        Ты - агент, который определяет стадию диалога пользователя.
        
        Доступные стадии:
        - greeting: приветствие, начало диалога
        - booking: запрос на бронирование, создание записи
        - cancel_booking: отмена существующей записи
        - reschedule: перенос записи на другое время
        - general: общий вопрос, не связанный с бронированием
        - unknown: не удалось определить стадию
        
        Проанализируй запрос пользователя и определи стадию диалога.
        Верни ответ в формате JSON с полями: stage, confidence, extracted_info.
        """
        
        super().__init__(
            langgraph_service=langgraph_service,
            instruction=instruction,
            response_format=StageDetection
        )
    
    def detect_stage(self, message: str, thread) -> StageDetection:
        """Определение стадии диалога"""
        response = self(message, thread)
        
        # Парсим JSON ответ
        if isinstance(response, StageDetection):
            return response
        
        # Если ответ строка, пытаемся распарсить
        import json
        try:
            # Извлекаем JSON из ответа
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                data = json.loads(json_str)
                return StageDetection(**data)
        except:
            pass
        
        # Fallback
        return StageDetection(stage="unknown", confidence=0.0)
```

**Проблема:** В текущей версии SDK может не быть `response_format` для структурного вывода. В этом случае нужно использовать Function Calling:

```python
class DetectStageFunction(BaseModel):
    """Функция для определения стадии"""
    stage: str = Field(description="Стадия диалога")
    confidence: float = Field(description="Уверенность", default=0.5)
    extracted_info: Optional[dict] = Field(default=None)
    
    def process(self, thread):
        return self  # Возвращаем сам объект
```

---

## Этап 4: Создание специализированных агентов

### 4.1. Инструменты для работы с системой

**Файл: `src/agents/tools/booking_tools.py`** (новый)

```python
"""
Инструменты для работы с системой бронирования
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class CheckAvailableSlots(BaseModel):
    """Проверка доступных слотов"""
    date: str = Field(description="Дата в формате YYYY-MM-DD")
    service_type: Optional[str] = Field(description="Тип услуги", default=None)
    
    def process(self, thread):
        # TODO: Реализовать обращение к API системы бронирования
        # Пока заглушка
        return f"Доступные слоты на {self.date}: 10:00, 11:00, 14:00, 16:00"

class CreateBooking(BaseModel):
    """Создание бронирования"""
    date: str = Field(description="Дата в формате YYYY-MM-DD")
    time: str = Field(description="Время в формате HH:MM")
    service_type: str = Field(description="Тип услуги")
    client_name: Optional[str] = Field(description="Имя клиента", default=None)
    client_phone: Optional[str] = Field(description="Телефон клиента", default=None)
    
    def process(self, thread):
        # TODO: Реализовать создание бронирования через API
        booking_id = f"BK-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        return f"Бронирование создано! ID: {booking_id}. Дата: {self.date}, время: {self.time}"

class GetBooking(BaseModel):
    """Получение информации о бронировании"""
    booking_id: Optional[str] = Field(description="ID бронирования", default=None)
    phone: Optional[str] = Field(description="Телефон клиента", default=None)
    
    def process(self, thread):
        # TODO: Реализовать получение бронирования через API
        return "Информация о бронировании: ..."

class CancelBooking(BaseModel):
    """Отмена бронирования"""
    booking_id: str = Field(description="ID бронирования")
    reason: Optional[str] = Field(description="Причина отмены", default=None)
    
    def process(self, thread):
        # TODO: Реализовать отмену бронирования через API
        return f"Бронирование {self.booking_id} отменено"

class RescheduleBooking(BaseModel):
    """Перенос бронирования"""
    booking_id: str = Field(description="ID бронирования")
    new_date: str = Field(description="Новая дата в формате YYYY-MM-DD")
    new_time: str = Field(description="Новое время в формате HH:MM")
    
    def process(self, thread):
        # TODO: Реализовать перенос бронирования через API
        return f"Бронирование {self.booking_id} перенесено на {self.new_date} {self.new_time}"
```

### 4.2. Агент бронирования

**Файл: `src/agents/booking_agent.py`** (новый)

```python
"""
Агент для обработки бронирований
"""
from .base_agent import BaseAgent
from .tools.booking_tools import (
    CheckAvailableSlots,
    CreateBooking,
    GetBooking
)
from ..services.langgraph_service import LangGraphService

class BookingAgent(BaseAgent):
    """Агент для работы с бронированиями"""
    
    def __init__(self, langgraph_service: LangGraphService):
        instruction = """
        Ты - агент по бронированию в салоне красоты LOOKTOWN.
        Твоя задача - помочь клиенту забронировать услугу.
        
        Ты можешь:
        1. Показать доступные слоты на определённую дату
        2. Создать бронирование
        3. Получить информацию о существующем бронировании
        
        Будь вежлив, уточняй детали если нужно.
        Используй инструменты для работы с системой бронирования.
        """
        
        super().__init__(
            langgraph_service=langgraph_service,
            instruction=instruction,
            tools=[CheckAvailableSlots, CreateBooking, GetBooking]
        )
```

### 4.3. Агент отмены записи

**Файл: `src/agents/cancel_booking_agent.py`** (новый)

```python
"""
Агент для отмены бронирований
"""
from .base_agent import BaseAgent
from .tools.booking_tools import CancelBooking, GetBooking
from ..services.langgraph_service import LangGraphService

class CancelBookingAgent(BaseAgent):
    """Агент для отмены бронирований"""
    
    def __init__(self, langgraph_service: LangGraphService):
        instruction = """
        Ты - агент по отмене бронирований в салоне красоты LOOKTOWN.
        Твоя задача - помочь клиенту отменить запись.
        
        Ты можешь:
        1. Найти бронирование по ID или телефону
        2. Отменить бронирование
        
        Будь вежлив, уточняй детали если нужно.
        Подтверждай отмену перед выполнением.
        """
        
        super().__init__(
            langgraph_service=langgraph_service,
            instruction=instruction,
            tools=[GetBooking, CancelBooking]
        )
```

### 4.4. Агент переноса записи

**Файл: `src/agents/reschedule_agent.py`** (новый)

```python
"""
Агент для переноса бронирований
"""
from .base_agent import BaseAgent
from .tools.booking_tools import RescheduleBooking, GetBooking, CheckAvailableSlots
from ..services.langgraph_service import LangGraphService

class RescheduleAgent(BaseAgent):
    """Агент для переноса бронирований"""
    
    def __init__(self, langgraph_service: LangGraphService):
        instruction = """
        Ты - агент по переносу бронирований в салоне красоты LOOKTOWN.
        Твоя задача - помочь клиенту перенести запись на другое время.
        
        Ты можешь:
        1. Найти бронирование по ID или телефону
        2. Показать доступные слоты на новую дату
        3. Перенести бронирование
        
        Будь вежлив, уточняй детали если нужно.
        Подтверждай перенос перед выполнением.
        """
        
        super().__init__(
            langgraph_service=langgraph_service,
            instruction=instruction,
            tools=[GetBooking, CheckAvailableSlots, RescheduleBooking]
        )
```

### 4.5. Агент приветствия

**Файл: `src/agents/greeting_agent.py`** (новый)

```python
"""
Агент для приветствия
"""
from .base_agent import BaseAgent
from ..services.langgraph_service import LangGraphService

class GreetingAgent(BaseAgent):
    """Агент для приветствия"""
    
    def __init__(self, langgraph_service: LangGraphService):
        instruction = """
        Ты - приветственный агент салона красоты LOOKTOWN.
        Твоя задача - поприветствовать клиента и помочь ему начать диалог.
        
        Будь дружелюбен и профессиональен.
        Предложи клиенту варианты: забронировать услугу, узнать информацию, и т.д.
        """
        
        super().__init__(
            langgraph_service=langgraph_service,
            instruction=instruction,
            tools=[]
        )
```

---

## Этап 5: Создание LangGraph графа

### 5.1. Определение состояния

**Файл: `src/graph/booking_state.py`** (новый)

```python
"""
Состояние для графа бронирования
"""
from typing import TypedDict, Optional
from yandex_cloud_ml_sdk._threads.thread import Thread
from ..agents.dialogue_stages import DialogueStage

class BookingState(TypedDict):
    """Состояние графа бронирования"""
    message: str                    # Исходное сообщение пользователя
    thread: Thread                  # Thread для всех агентов (общая история)
    stage: Optional[str]            # Определённая стадия диалога
    extracted_info: Optional[dict]  # Извлечённая информация
    answer: str                     # Финальный ответ пользователю
    manager_alert: Optional[str]    # Сообщение для менеджера (если нужно)
```

### 5.2. Узлы графа

**Файл: `src/graph/booking_graph.py`** (новый)

```python
"""
Граф состояний для обработки бронирований
"""
from typing import Literal
from langgraph.graph import StateGraph, START, END
from .booking_state import BookingState
from ..agents.stage_detector_agent import StageDetectorAgent
from ..agents.booking_agent import BookingAgent
from ..agents.cancel_booking_agent import CancelBookingAgent
from ..agents.reschedule_agent import RescheduleAgent
from ..agents.greeting_agent import GreetingAgent
from ..services.langgraph_service import LangGraphService
from ..services.logger_service import logger

class BookingGraph:
    """Граф состояний для обработки бронирований"""
    
    def __init__(self, langgraph_service: LangGraphService):
        self.langgraph_service = langgraph_service
        
        # Создаём агентов
        self.stage_detector = StageDetectorAgent(langgraph_service)
        self.booking_agent = BookingAgent(langgraph_service)
        self.cancel_agent = CancelBookingAgent(langgraph_service)
        self.reschedule_agent = RescheduleAgent(langgraph_service)
        self.greeting_agent = GreetingAgent(langgraph_service)
        
        # Создаём граф
        self.graph = self._create_graph()
        self.compiled_graph = self.graph.compile()
    
    def _create_graph(self) -> StateGraph:
        """Создание графа состояний"""
        graph = StateGraph(BookingState)
        
        # Добавляем узлы
        graph.add_node("detect_stage", self._detect_stage)
        graph.add_node("handle_greeting", self._handle_greeting)
        graph.add_node("handle_booking", self._handle_booking)
        graph.add_node("handle_cancel", self._handle_cancel)
        graph.add_node("handle_reschedule", self._handle_reschedule)
        
        # Добавляем рёбра
        graph.add_edge(START, "detect_stage")
        graph.add_conditional_edges(
            "detect_stage",
            self._route_by_stage,
            {
                "greeting": "handle_greeting",
                "booking": "handle_booking",
                "cancel_booking": "handle_cancel",
                "reschedule": "handle_reschedule",
                "general": "handle_greeting",  # Общие вопросы обрабатываем как приветствие
                "unknown": "handle_greeting"    # Неопределённые тоже
            }
        )
        graph.add_edge("handle_greeting", END)
        graph.add_edge("handle_booking", END)
        graph.add_edge("handle_cancel", END)
        graph.add_edge("handle_reschedule", END)
        
        return graph
    
    def _detect_stage(self, state: BookingState) -> BookingState:
        """Узел определения стадии"""
        logger.info("Определение стадии диалога", state.get("thread", {}).id if hasattr(state.get("thread"), "id") else None)
        
        message = state["message"]
        thread = state["thread"]
        
        # Определяем стадию
        stage_detection = self.stage_detector.detect_stage(message, thread)
        
        return {
            "stage": stage_detection.stage,
            "extracted_info": stage_detection.extracted_info or {}
        }
    
    def _route_by_stage(self, state: BookingState) -> Literal["greeting", "booking", "cancel_booking", "reschedule", "general", "unknown"]:
        """Маршрутизация по стадии"""
        stage = state.get("stage", "unknown")
        return stage
    
    def _handle_greeting(self, state: BookingState) -> BookingState:
        """Обработка приветствия"""
        logger.info("Обработка приветствия")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.greeting_agent(message, thread)
        
        return {"answer": answer}
    
    def _handle_booking(self, state: BookingState) -> BookingState:
        """Обработка бронирования"""
        logger.info("Обработка бронирования")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.booking_agent(message, thread)
        
        return {"answer": answer}
    
    def _handle_cancel(self, state: BookingState) -> BookingState:
        """Обработка отмены"""
        logger.info("Обработка отмены")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.cancel_agent(message, thread)
        
        return {"answer": answer}
    
    def _handle_reschedule(self, state: BookingState) -> BookingState:
        """Обработка переноса"""
        logger.info("Обработка переноса")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.reschedule_agent(message, thread)
        
        return {"answer": answer}
    
    def invoke(self, state: BookingState) -> BookingState:
        """Выполнение графа"""
        return self.compiled_graph.invoke(state)
```

---

## Этап 6: Интеграция с существующим сервисом

### 6.1. Обновление YandexAgentService

**Файл: `src/services/yandex_agent_service.py`**

Добавить новый метод для работы с LangGraph:

```python
from ..graph.booking_graph import BookingGraph
from ..services.langgraph_service import LangGraphService
from ..ydb_client import get_ydb_client

class YandexAgentService:
    # ... существующий код ...
    
    def __init__(self, auth_service, debug_service, escalation_service):
        # ... существующий код ...
        
        # Инициализация LangGraph сервиса
        self.langgraph_service = LangGraphService()
        self.booking_graph = BookingGraph(self.langgraph_service)
        self.use_langgraph = os.getenv("USE_LANGGRAPH", "false").lower() == "true"
    
    async def send_to_agent_langgraph(self, chat_id: str, user_text: str) -> dict:
        """Отправка сообщения через LangGraph (новый метод)"""
        try:
            from ..graph.booking_state import BookingState
            
            # Получаем или создаём Thread
            ydb_client = get_ydb_client()
            thread_id = await asyncio.to_thread(ydb_client.get_thread_id, chat_id)
            
            if thread_id:
                thread = self.langgraph_service.get_thread_by_id(thread_id)
                if not thread:
                    # Thread не найден, создаём новый
                    thread = self.langgraph_service.create_thread()
                    await asyncio.to_thread(ydb_client.save_thread_id, chat_id, thread.id)
            else:
                # Создаём новый Thread
                thread = self.langgraph_service.create_thread()
                await asyncio.to_thread(ydb_client.save_thread_id, chat_id, thread.id)
            
            # Добавляем московское время
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
            
            # Нормализуем даты и время
            from .date_normalizer import normalize_dates_in_text
            from .time_normalizer import normalize_times_in_text
            
            answer = normalize_dates_in_text(answer)
            answer = normalize_times_in_text(answer)
            
            result = {"user_message": answer}
            if manager_alert:
                result["manager_alert"] = normalize_dates_in_text(
                    normalize_times_in_text(manager_alert)
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка в LangGraph: {e}")
            # Fallback к старому методу
            return await self.send_to_agent(chat_id, user_text)
    
    async def send_to_agent(self, chat_id: str, user_text: str) -> dict:
        """Отправка сообщения агенту (обновлённый метод)"""
        # Если включён LangGraph, используем его
        if self.use_langgraph:
            return await self.send_to_agent_langgraph(chat_id, user_text)
        
        # Иначе используем старый метод с Responses API
        # ... существующий код ...
    
    async def reset_context(self, chat_id: str):
        """Сброс контекста (обновлённый метод)"""
        try:
            ydb_client = get_ydb_client()
            
            # Сбрасываем и previous_response_id, и thread_id
            await asyncio.to_thread(ydb_client.reset_context, chat_id)
            await asyncio.to_thread(ydb_client.reset_thread, chat_id)
            
            logger.ydb("Контекст сброшен", chat_id)
        except Exception as e:
            logger.error("Ошибка при сбросе контекста", str(e))
```

---

## Этап 7: Обновление структуры проекта

### 7.1. Новая структура папок

```
src/
├── agents/
│   ├── __init__.py
│   ├── base_agent.py
│   ├── stage_detector_agent.py
│   ├── booking_agent.py
│   ├── cancel_booking_agent.py
│   ├── reschedule_agent.py
│   ├── greeting_agent.py
│   ├── dialogue_stages.py
│   └── tools/
│       ├── __init__.py
│       └── booking_tools.py
├── graph/
│   ├── __init__.py
│   ├── booking_state.py
│   └── booking_graph.py
├── services/
│   ├── ... (существующие сервисы)
│   └── langgraph_service.py (новый)
└── ... (остальные файлы)
```

### 7.2. Обновление service_factory

**Файл: `service_factory.py`**

Добавить создание LangGraphService:

```python
from src.services import LangGraphService

class ServiceFactory:
    def __init__(self):
        # ... существующие сервисы ...
        self._langgraph_service = None
    
    def get_langgraph_service(self) -> LangGraphService:
        """Получить экземпляр LangGraphService"""
        if self._langgraph_service is None:
            self._langgraph_service = LangGraphService()
        return self._langgraph_service
```

---

## Этап 8: Переменные окружения

### 8.1. Добавление новых переменных

**Файл: `.env`** (пример)

```env
# Существующие переменные
TELEGRAM_BOT_TOKEN=...
YANDEX_API_KEY_SECRET=...
YANDEX_FOLDER_ID=...
YDB_ENDPOINT=...
YDB_DATABASE=...

# Новые переменные для LangGraph
USE_LANGGRAPH=true  # Включить использование LangGraph (по умолчанию false)
```

---

## Этап 9: Миграция данных

### 9.1. Скрипт миграции YDB

**Файл: `scripts/migrate_to_threads.py`** (новый, опционально)

```python
"""
Скрипт для миграции с previous_response_id на thread_id
"""
from src.ydb_client import get_ydb_client
from src.services.langgraph_service import LangGraphService

def migrate_chat_to_thread(chat_id: str):
    """Миграция одного чата на Thread"""
    ydb_client = get_ydb_client()
    langgraph_service = LangGraphService()
    
    # Проверяем, есть ли уже thread_id
    existing_thread_id = ydb_client.get_thread_id(chat_id)
    if existing_thread_id:
        print(f"Chat {chat_id} уже имеет thread_id")
        return
    
    # Создаём новый Thread
    thread = langgraph_service.create_thread()
    
    # Сохраняем thread_id
    ydb_client.save_thread_id(chat_id, thread.id)
    
    print(f"Chat {chat_id} мигрирован на thread_id: {thread.id}")

# Можно запустить для всех чатов или по требованию
```

---

## Этап 10: Тестирование

### 10.1. Поэтапное включение

1. **Фаза 1:** Создать все компоненты, но оставить `USE_LANGGRAPH=false`
2. **Фаза 2:** Протестировать отдельные агенты
3. **Фаза 3:** Протестировать граф на тестовых данных
4. **Фаза 4:** Включить для одного тестового пользователя (`USE_LANGGRAPH=true`)
5. **Фаза 5:** Полное включение

### 10.2. Проверка работы Thread

- Все агенты должны видеть историю диалога
- При переходе между стадиями контекст сохраняется
- При сбросе контекста Thread удаляется

---

## Ключевые моменты интеграции

### ✅ Преимущества нового подхода:

1. **Единая история диалога** - все агенты видят полный контекст через Thread
2. **Модульность** - каждый агент отвечает за свою задачу
3. **Гибкость** - легко добавлять новые стадии и агентов
4. **Масштабируемость** - можно добавлять новые инструменты и функции

### ⚠️ Важные замечания:

1. **Обратная совместимость** - старый метод с Responses API остаётся как fallback
2. **Миграция Thread** - нужно создать Thread для существующих пользователей при первом обращении
3. **Управление жизненным циклом** - Thread имеет TTL, нужно следить за удалением
4. **Ошибки** - при ошибках в LangGraph должен быть fallback к старому методу

### 🔄 Процесс работы:

```
Пользователь → Telegram Bot
                ↓
         YandexAgentService
                ↓
    [USE_LANGGRAPH=true?]
         ↓              ↓
    LangGraph      Responses API
         ↓              ↓
    StageDetector  (старый метод)
         ↓
    Route по стадии
         ↓
    Специализированный агент
         ↓
    Thread (общая история)
         ↓
    Ответ пользователю
```

---

## Следующие шаги

1. ✅ Установить зависимости (`yandex-cloud-ml-sdk`, `langgraph`, `pydantic`)
2. ✅ Создать базовые компоненты (`LangGraphService`, `BaseAgent`)
3. ✅ Создать агента определения стадии
4. ✅ Создать специализированных агентов
5. ✅ Создать граф состояний
6. ✅ Интегрировать с существующим сервисом
7. ✅ Обновить YDB схему
8. ✅ Протестировать поэтапно
9. ✅ Включить для продакшена

---

*План составлен на основе анализа проекта и архитектуры YC Wine Assistant*

