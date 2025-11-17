"""
Streamlit Playground для тестирования LangGraph агентов
"""
import sys
import os

# Проверяем, что скрипт запущен через Streamlit
# Если запущен напрямую через Python, показываем ошибку
if __name__ == "__main__" and "streamlit" not in sys.modules:
    print("❌ Ошибка: Этот скрипт должен запускаться через Streamlit!")
    print("\n📝 Правильный способ запуска:")
    print("   python run_playground.py")
    print("\n   или")
    print("\n   streamlit run playground.py")
    sys.exit(1)

import streamlit as st
from dotenv import load_dotenv
import json
from datetime import datetime

# Загружаем переменные окружения
load_dotenv()

# Функция для форматирования текста с сохранением переносов строк
def format_text_with_line_breaks(text: str) -> str:
    """
    Форматирует текст так, чтобы одинарные переносы строк отображались в Markdown.
    В Markdown для переноса строки нужно два пробела в конце строки.
    """
    if not isinstance(text, str):
        return str(text)
    
    # Сначала заменяем двойные переносы на специальный маркер, чтобы их не трогать
    text = text.replace('\n\n', '\x00\x00')
    
    # Заменяем все одинарные переносы на два пробела + перенос
    text = text.replace('\n', '  \n')
    
    # Восстанавливаем двойные переносы (они создают абзацы в Markdown)
    text = text.replace('\x00\x00', '\n\n')
    
    return text

# Импорты для работы с агентами
from src.services.langgraph_service import LangGraphService
from src.graph.main_graph import MainGraph
from src.graph.conversation_state import ConversationState
from src.agents.dialogue_stages import DialogueStage
from src.services.llm_request_logger import llm_request_logger
from src.services.retry_service import RetryService
from src.services.call_manager_service import CallManagerException

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
        
        # Создаём сервис для Playground
        st.session_state.langgraph_service = LangGraphService()
        # Очищаем кэш перед созданием нового графа, чтобы агенты пересоздались с актуальными инструментами
        MainGraph.clear_cache()
        st.session_state.main_graph = MainGraph(st.session_state.langgraph_service)
        st.session_state.conversation_history = []
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
    
    # Информация о conversation_history
    if st.session_state.conversation_history:
        st.info(f"**История сообщений:**\n`{len(st.session_state.conversation_history)} сообщений`")
    
    # Информация о текущем файле лога (если есть активный запрос)
    if llm_request_logger.current_log_file:
        log_file_name = llm_request_logger.current_log_file.name
        st.info(f"**Текущий лог файл:**\n`{log_file_name}`")
    
    # Кнопка сброса диалога
    if st.button("🔄 Сбросить диалог", type="secondary"):
        # Закрываем текущий файл лога если есть
        if llm_request_logger.current_log_file:
            try:
                with open(llm_request_logger.current_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n{'='*80}\n")
                    f.write(f"DIALOG RESET BY USER\n")
                    f.write(f"{'='*80}\n")
            except:
                pass
            llm_request_logger.current_log_file = None
        
        st.session_state.conversation_history = []
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
            st.markdown(format_text_with_line_breaks(content))
            
            # Показываем метаданные если есть
            if "metadata" in message:
                # Показываем стадию сразу, если есть
                if "stage" in message["metadata"] and message["metadata"]["stage"]:
                    stage_emoji = {
                        "greeting": "👋",
                        "booking": "📅",
                        "cancel_booking": "❌",
                        "reschedule": "🔄",
                        "salon_info": "ℹ️",
                        "general": "💬",
                        "unknown": "❓"
                    }.get(message["metadata"]["stage"], "❓")
                    st.caption(f"{stage_emoji} **Стадия:** `{message['metadata']['stage']}`")
                
                # Показываем агента сразу, если есть
                if "agent_name" in message["metadata"] and message["metadata"]["agent_name"]:
                    st.caption(f"🤖 **Агент:** `{message['metadata']['agent_name']}`")
                
                # Показываем использованные инструменты сразу, если есть
                if "used_tools" in message["metadata"] and message["metadata"]["used_tools"]:
                    tools = message["metadata"]["used_tools"]
                    tools_text = ", ".join([f"`{tool}`" for tool in tools])
                    st.caption(f"🔧 **Инструменты:** {tools_text}")
                elif "used_tools" in message["metadata"]:
                    st.caption("🔧 **Инструменты:** нет")
                
                # Показываем детали инструментов в expandable секции для сохранённых сообщений
                if "tool_calls_results" in message["metadata"] and message["metadata"]["tool_calls_results"]:
                    tool_calls_results = message["metadata"]["tool_calls_results"]
                    with st.expander("🔍 Детали ответа", expanded=False):
                        st.markdown("### 📋 Ответы от инструментов:")
                        for tool_call in tool_calls_results:
                            tool_name = tool_call.get('name', 'Unknown')
                            tool_args = tool_call.get('args', {})
                            tool_result = tool_call.get('result', 'N/A')
                            
                            with st.expander(f"🔧 {tool_name}", expanded=False):
                                st.markdown(f"**Аргументы:**")
                                st.json(tool_args)
                                st.markdown(f"**Результат:**")
                                # Форматируем результат в зависимости от типа
                                if isinstance(tool_result, str):
                                    try:
                                        import json
                                        parsed = json.loads(tool_result)
                                        st.json(parsed)
                                    except (json.JSONDecodeError, TypeError):
                                        st.text(tool_result)
                                elif isinstance(tool_result, (dict, list)):
                                    st.json(tool_result)
                                else:
                                    st.text(str(tool_result))

# Поле ввода
user_input = st.chat_input("Введите сообщение...")

if user_input:
    # Начинаем новый запрос - создаём новый файл лога
    log_file = llm_request_logger.start_new_request()
    
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
                initial_state: ConversationState = {
                    "message": user_input,
                    "conversation_history": st.session_state.get("conversation_history", []),
                    "stage": None,
                    "extracted_info": None,
                    "answer": "",
                    "manager_alert": None,
                    "agent_name": None,
                    "used_tools": None
                }
                
                # Функция для выполнения графа (для retry на нижнем уровне)
                def _execute_graph():
                    """Внутренняя функция для выполнения графа"""
                    return st.session_state.main_graph.compiled_graph.invoke(initial_state)
                
                # Выполняем граф с retry на нижнем уровне
                result_state = RetryService.execute_with_retry(
                    operation=_execute_graph,
                    max_retries=3,
                    operation_name="выполнение графа в Playground",
                    context_info={
                        "message": user_input,
                        "chat_id": "playground"
                    }
                )
                
                # Завершаем запрос - добавляем финальную запись в лог
                try:
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"\n{'='*80}\n")
                        f.write(f"REQUEST COMPLETED SUCCESSFULLY\n")
                        f.write(f"Final Answer: {result_state.get('answer', 'N/A')[:200]}\n")
                        f.write(f"Agent: {result_state.get('agent_name', 'N/A')}\n")
                        f.write(f"Stage: {result_state.get('stage', 'N/A')}\n")
                        f.write(f"{'='*80}\n")
                except:
                    pass
                
                # Показываем стадию сразу после определения
                detected_stage = result_state.get("stage")
                if detected_stage:
                    stage_emoji = {
                        "greeting": "👋",
                        "booking": "📅",
                        "cancel_booking": "❌",
                        "reschedule": "🔄",
                        "salon_info": "ℹ️",
                        "general": "💬",
                        "unknown": "❓"
                    }.get(detected_stage, "❓")
                    st.info(f"{stage_emoji} **Определена стадия:** `{detected_stage}`")
                
                # Сохраняем состояние графа
                graph_state_copy = {
                    "stage": detected_stage,
                    "timestamp": datetime.now().isoformat()
                }
                st.session_state.graph_states.append(graph_state_copy)
                
                # Получаем ответ
                answer = result_state.get("answer", "Не получен ответ")
                agent_name = result_state.get("agent_name", "Unknown")
                used_tools = result_state.get("used_tools", [])
                
                # Получаем полные результаты инструментов из агента
                tool_calls_results = []
                if agent_name and hasattr(st.session_state.main_graph, '_get_agent_by_name'):
                    agent = st.session_state.main_graph._get_agent_by_name(agent_name)
                    if agent and hasattr(agent, '_last_tool_calls') and agent._last_tool_calls:
                        tool_calls_results = agent._last_tool_calls
                else:
                    # Альтернативный способ получения tool_calls из графа
                    agent_map = {
                        "GreetingAgent": getattr(st.session_state.main_graph, 'greeting_agent', None),
                        "BookingAgent": getattr(st.session_state.main_graph, 'booking_agent', None),
                        "BookingToMasterAgent": getattr(st.session_state.main_graph, 'booking_to_master_agent', None),
                        "CancelBookingAgent": getattr(st.session_state.main_graph, 'cancel_agent', None),
                        "RescheduleAgent": getattr(st.session_state.main_graph, 'reschedule_agent', None),
                        "ViewMyBookingAgent": getattr(st.session_state.main_graph, 'view_my_booking_agent', None),
                        "InformationGatheringAgent": getattr(st.session_state.main_graph, 'information_gathering_agent', None),
                    }
                    agent = agent_map.get(agent_name)
                    if agent and hasattr(agent, '_last_tool_calls') and agent._last_tool_calls:
                        tool_calls_results = agent._last_tool_calls
                
                # Показываем ответ
                st.markdown(format_text_with_line_breaks(answer))
                
                # Показываем какой агент дал ответ
                st.caption(f"🤖 **Ответ от агента:** `{agent_name}`")
                
                # Показываем использованные инструменты
                if used_tools:
                    tools_text = ", ".join([f"`{tool}`" for tool in used_tools])
                    st.caption(f"🔧 **Использованные инструменты:** {tools_text}")
                else:
                    st.caption("🔧 **Использованные инструменты:** нет")
                
                # Показываем метаданные в expandable секции
                with st.expander("🔍 Детали ответа", expanded=False):
                    if used_tools:
                        st.info(f"**Использованные инструменты:** {', '.join(used_tools)}")
                    
                    # Показываем полные ответы от инструментов
                    if tool_calls_results:
                        st.markdown("### 📋 Ответы от инструментов:")
                        for i, tool_call in enumerate(tool_calls_results, 1):
                            tool_name = tool_call.get('name', 'Unknown')
                            tool_args = tool_call.get('args', {})
                            tool_result = tool_call.get('result', 'N/A')
                            
                            with st.expander(f"🔧 {tool_name}", expanded=True):
                                st.markdown(f"**Аргументы:**")
                                st.json(tool_args)
                                st.markdown(f"**Результат:**")
                                # Форматируем результат в зависимости от типа
                                if isinstance(tool_result, str):
                                    # Пытаемся распарсить JSON, если это строка
                                    try:
                                        parsed = json.loads(tool_result)
                                        st.json(parsed)
                                    except (json.JSONDecodeError, TypeError):
                                        st.text(tool_result)
                                elif isinstance(tool_result, (dict, list)):
                                    st.json(tool_result)
                                else:
                                    st.text(str(tool_result))
                    
                    if result_state.get("manager_alert"):
                        st.warning(f"**Alert для менеджера:** {result_state['manager_alert']}")
                
                # Добавляем сообщение ассистента
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {
                        "stage": detected_stage,
                        "agent_name": agent_name,
                        "used_tools": used_tools,
                        "tool_calls_results": tool_calls_results
                    }
                })
                
                # Обновляем conversation_history
                if "conversation_history" in result_state:
                    st.session_state.conversation_history = result_state["conversation_history"]
                
                # Показываем историю conversation_history
                with st.expander("📜 История диалога (последние 10 сообщений)", expanded=False):
                    history = st.session_state.get("conversation_history", [])
                    for msg in reversed(history[-10:]):
                        role = msg.get("role", "unknown")
                        content = msg.get("content", "")
                        role_emoji = "👤" if role == "user" else "🤖"
                        st.text(f"{role_emoji} **{role.upper()}:** {content[:300]}")
                
            except CallManagerException as e:
                # Обрабатываем вызов CallManager - показываем сообщение пользователю и alert менеджеру
                escalation_result = e.escalation_result
                user_message = escalation_result.get("user_message")
                manager_alert = escalation_result.get("manager_alert")
                
                # Завершаем запрос с CallManager
                try:
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"\n{'='*80}\n")
                        f.write(f"REQUEST COMPLETED WITH CALL_MANAGER\n")
                        f.write(f"User Message: {user_message}\n")
                        if manager_alert:
                            f.write(f"Manager Alert: {manager_alert[:200]}\n")
                        f.write(f"{'='*80}\n")
                except Exception:
                    pass
                
                # Показываем сообщение пользователю
                st.markdown(format_text_with_line_breaks(user_message))
                
                # Показываем alert менеджера если есть
                if manager_alert:
                    st.warning(f"**Alert для менеджера:** {manager_alert}")
                
                # Добавляем сообщение ассистента
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": user_message,
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {
                        "call_manager": True,
                        "manager_alert": manager_alert
                    }
                })
                
            except Exception as e:
                # Завершаем запрос с ошибкой
                try:
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"\n{'='*80}\n")
                        f.write(f"REQUEST COMPLETED WITH ERROR\n")
                        f.write(f"Error: {str(e)}\n")
                        import traceback
                        f.write(f"Traceback:\n{traceback.format_exc()}\n")
                        f.write(f"{'='*80}\n")
                except:
                    pass
                
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

# Динамически получаем стадии из enum
stages_list = [stage.value for stage in DialogueStage]
stages_text = ", ".join([f"`{stage}`" for stage in stages_list])

# Динамически получаем список агентов из MainGraph
try:
    # Получаем агентов из кэша MainGraph
    agents_list = []
    if hasattr(st.session_state, 'main_graph') and st.session_state.main_graph:
        # Получаем все агенты из графа
        agents_list.append("StageDetectorAgent")
        if hasattr(st.session_state.main_graph, 'greeting_agent'):
            agents_list.append("GreetingAgent")
        if hasattr(st.session_state.main_graph, 'booking_agent'):
            agents_list.append("BookingAgent")
        if hasattr(st.session_state.main_graph, 'cancel_agent'):
            agents_list.append("CancelBookingAgent")
        if hasattr(st.session_state.main_graph, 'reschedule_agent'):
            agents_list.append("RescheduleAgent")
        if hasattr(st.session_state.main_graph, 'salon_info_agent'):
            agents_list.append("SalonInfoAgent")
    
    # Если список пустой, используем дефолтный
    if not agents_list:
        agents_list = ["StageDetectorAgent", "GreetingAgent", "BookingAgent", "CancelBookingAgent", "RescheduleAgent"]
    
    agents_text = ", ".join([f"`{agent}`" for agent in agents_list])
except Exception:
    # Fallback к дефолтному списку
    agents_text = "`StageDetectorAgent`, `GreetingAgent`, `BookingAgent`, `CancelBookingAgent`, `RescheduleAgent`"

st.markdown(f"""
### 📝 Информация
- **Thread ID:** Используется для сохранения контекста диалога
- **Стадии:** {stages_text}
- **Инструменты:** `GetCategories`, `GetServices`, `FindSlots`
- **Агенты:** {agents_text}
""")


