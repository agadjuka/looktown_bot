"""
Streamlit Playground для тестирования LangGraph агентов
"""
import streamlit as st
import os
from dotenv import load_dotenv
import json
from datetime import datetime
import sys

# Загружаем переменные окружения
load_dotenv()

# Импорты для работы с агентами
from src.services.langgraph_service import LangGraphService
from src.graph.booking_graph import BookingGraph
from src.graph.booking_state import BookingState
from src.agents.dialogue_stages import DialogueStage

# Перехватываем вызовы инструментов через monkey patching
def patch_base_agent():
    """Патчим BaseAgent для отслеживания вызовов инструментов"""
    from src.agents.base_agent import BaseAgent
    
    original_call = BaseAgent.__call__
    
    def patched_call(self, message: str, thread):
        """Обёртка для отслеживания вызовов инструментов"""
        result = original_call(self, message, thread)
        
        # Сохраняем tool_calls в session_state если они есть
        if hasattr(self, '_last_tool_calls') and self._last_tool_calls:
            if 'tool_calls_history' in st.session_state:
                for tool_call in self._last_tool_calls:
                    st.session_state.tool_calls_history.append({
                        'name': tool_call.get('name', 'Unknown'),
                        'args': tool_call.get('args', {}),
                        'result': tool_call.get('result', 'N/A'),
                        'time': datetime.now().strftime('%H:%M:%S'),
                        'agent': self.__class__.__name__
                    })
        
        return result
    
    BaseAgent.__call__ = patched_call

# Настройка страницы
st.set_page_config(
    page_title="LangGraph Agent Playground",
    page_icon="🤖",
    layout="wide"
)

# Инициализация сессии
if "langgraph_service" not in st.session_state:
    try:
        # Применяем патч для отслеживания инструментов
        patch_base_agent()
        
        st.session_state.langgraph_service = LangGraphService()
        st.session_state.booking_graph = BookingGraph(st.session_state.langgraph_service)
        st.session_state.thread = st.session_state.langgraph_service.create_thread()
        st.session_state.messages = []
        st.session_state.tool_calls_history = []
        st.session_state.graph_states = []
    except Exception as e:
        st.error(f"Ошибка инициализации: {e}")
        import traceback
        st.code(traceback.format_exc())
        st.stop()

# Заголовок
st.title("🤖 LangGraph Agent Playground")
st.markdown("Тестирование агентов бронирования LOOKTOWN")

# Боковая панель с настройками
with st.sidebar:
    st.header("⚙️ Настройки")
    
    # Информация о Thread
    if st.session_state.thread:
        st.info(f"**Thread ID:**\n`{st.session_state.thread.id}`")
    
    # Кнопка сброса диалога
    if st.button("🔄 Сбросить диалог", type="secondary"):
        st.session_state.thread = st.session_state.langgraph_service.create_thread()
        st.session_state.messages = []
        st.session_state.tool_calls_history = []
        st.session_state.graph_states = []
        st.rerun()
    
    st.divider()
    
    # Показываем историю вызовов инструментов
    st.header("🔧 История инструментов")
    if st.session_state.tool_calls_history:
        for i, tool_call in enumerate(reversed(st.session_state.tool_calls_history[-10:])):
            agent_name = tool_call.get('agent', 'Unknown')
            tool_name = tool_call.get('name', 'Unknown')
            with st.expander(f"🔧 {agent_name} → {tool_name}", expanded=False):
                st.text(f"**Время:** {tool_call.get('time', 'N/A')}")
                st.text(f"**Агент:** {agent_name}")
                st.json(tool_call.get('args', {}))
                st.text(f"**Результат:**")
                st.text(tool_call.get('result', 'N/A'))
    else:
        st.text("Пока нет вызовов")
    
    st.divider()
    
    # Показываем состояния графа
    st.header("📊 Состояния графа")
    if st.session_state.graph_states:
        for i, state in enumerate(reversed(st.session_state.graph_states[-5:])):
            with st.expander(f"Шаг {len(st.session_state.graph_states) - i}", expanded=False):
                if state.get('stage'):
                    st.info(f"**Стадия:** `{state['stage']}`")
                if state.get('extracted_info'):
                    st.json(state.get('extracted_info'))
                st.text(f"**Время:** {state.get('timestamp', 'N/A')}")
    else:
        st.text("Пока нет состояний")

# Основная область чата
st.header("💬 Диалог с агентом")

# Отображаем историю сообщений
chat_container = st.container()
with chat_container:
    for message in st.session_state.messages:
        role = message["role"]
        content = message["content"]
        
        with st.chat_message(role):
            st.markdown(content)
            
            # Показываем метаданные если есть
            if "metadata" in message:
                with st.expander("🔍 Детали", expanded=False):
                    if "stage" in message["metadata"]:
                        st.info(f"**Стадия:** `{message['metadata']['stage']}`")
                    if "extracted_info" in message["metadata"]:
                        st.json(message["metadata"]["extracted_info"])

# Поле ввода
user_input = st.chat_input("Введите сообщение...")

if user_input:
    # Добавляем сообщение пользователя
    st.session_state.messages.append({
        "role": "user",
        "content": user_input,
        "timestamp": datetime.now().isoformat()
    })
    
    # Показываем сообщение пользователя
    with st.chat_message("user"):
        st.markdown(user_input)
    
    # Обрабатываем через граф
    with st.chat_message("assistant"):
        with st.spinner("Агент думает..."):
            try:
                # Создаём начальное состояние
                initial_state: BookingState = {
                    "message": user_input,
                    "thread": st.session_state.thread,
                    "stage": None,
                    "extracted_info": None,
                    "answer": "",
                    "manager_alert": None
                }
                
                # Выполняем граф
                result_state = st.session_state.booking_graph.invoke(initial_state)
                
                # Сохраняем состояние графа
                graph_state_copy = {
                    "stage": result_state.get("stage"),
                    "extracted_info": result_state.get("extracted_info"),
                    "timestamp": datetime.now().isoformat()
                }
                st.session_state.graph_states.append(graph_state_copy)
                
                # Получаем ответ
                answer = result_state.get("answer", "Не получен ответ")
                
                # Показываем ответ
                st.markdown(answer)
                
                # Показываем метаданные
                with st.expander("🔍 Детали ответа", expanded=False):
                    if result_state.get("stage"):
                        st.info(f"**Определённая стадия:** `{result_state['stage']}`")
                    if result_state.get("extracted_info"):
                        st.json(result_state["extracted_info"])
                    if result_state.get("manager_alert"):
                        st.warning(f"**Alert для менеджера:** {result_state['manager_alert']}")
                
                # Добавляем сообщение ассистента
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {
                        "stage": result_state.get("stage"),
                        "extracted_info": result_state.get("extracted_info")
                    }
                })
                
                # Показываем историю Thread
                with st.expander("📜 История Thread (последние 10 сообщений)", expanded=False):
                    thread_messages = list(st.session_state.thread)
                    for msg in reversed(thread_messages[-10:]):
                        role_emoji = "👤" if msg.author.role == "USER" else "🤖"
                        st.text(f"{role_emoji} **{msg.author.role}:** {msg.text[:300]}")
                
            except Exception as e:
                error_msg = f"Ошибка: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_msg,
                    "timestamp": datetime.now().isoformat()
                })
                
                # Показываем traceback
                import traceback
                with st.expander("🔍 Детали ошибки", expanded=False):
                    st.code(traceback.format_exc())

# Футер с информацией
st.divider()
st.markdown("""
### 📝 Информация
- **Thread ID:** Используется для сохранения контекста диалога
- **Стадии:** `greeting`, `booking`, `cancel_booking`, `reschedule`, `general`, `unknown`
- **Инструменты:** `CheckAvailableSlots`, `CreateBooking`, `GetBooking`, `CancelBooking`, `RescheduleBooking`
- **Агенты:** `StageDetectorAgent`, `GreetingAgent`, `BookingAgent`, `CancelBookingAgent`, `RescheduleAgent`
""")


