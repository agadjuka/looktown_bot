"""
Prompt Manager - веб-интерфейс для управления стадиями (агентами)
"""
import streamlit as st
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('prompt_manager.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)
logger.info("=== ЗАПУСК PROMPT MANAGER ===")

# Добавляем корень проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from prompt_manager.stage_manager import StageManager
from yandex_cloud_ml_sdk import YCloudML
from src.ydb_client import get_ydb_client

# Загружаем переменные окружения
load_dotenv()

# Настройка страницы
st.set_page_config(
    page_title="Prompt Manager",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Инициализация
if 'stage_manager' not in st.session_state:
    st.session_state.stage_manager = StageManager()
    st.session_state.langgraph_service = None
    st.session_state.ydb_client = None
    st.session_state.current_view = None  # 'detector' или индекс стадии

# Инициализация сервисов
try:
    folder_id = os.getenv("YANDEX_FOLDER_ID")
    api_key = os.getenv("YANDEX_API_KEY_SECRET")
    if folder_id and api_key:
        st.session_state.langgraph_service = YCloudML(folder_id=folder_id, auth=api_key)
        st.session_state.ydb_client = get_ydb_client()
except Exception as e:
    st.warning(f"Не удалось инициализировать сервисы: {e}")

# Боковая панель - навигация
with st.sidebar:
    st.title("📝 Prompt Manager")
    
    # Кнопка обновления
    if st.button("🔄 Обновить", use_container_width=True):
        st.rerun()
    
    st.divider()
    
    # Определитель стадий
    if st.button("🎯 Определитель стадий", use_container_width=True, type="primary" if st.session_state.get('current_view') == 'detector' else "secondary"):
        st.session_state.current_view = 'detector'
        st.session_state.show_create_form = False
        st.session_state.show_delete_confirm = False
        st.rerun()
    
    st.divider()
    st.markdown("**Стадии:**")
    
    # Получаем все стадии
    stages = st.session_state.stage_manager.get_all_stages()
    
    if not stages:
        st.info("Стадии не найдены")
    else:
        for i, stage in enumerate(stages):
            if st.button(
                f"{stage['name']}",
                key=f"nav_stage_{i}",
                use_container_width=True,
                type="primary" if st.session_state.get('current_view') == i else "secondary"
            ):
                st.session_state.current_view = i
                st.session_state.show_create_form = False
                st.session_state.show_delete_confirm = False
                st.rerun()
    
    st.divider()
    
    # Кнопка создания
    if st.button("➕ Создать стадию", type="primary", use_container_width=True):
        st.session_state.current_view = 'create'
        st.session_state.show_create_form = True
        st.rerun()

# Основная область
if st.session_state.get('current_view') == 'detector':
    # Редактирование определителя стадий
    st.header("🎯 Определитель стадий")
    st.markdown("**Агент StageDetectorAgent** - определяет стадию диалога")
    
    current_detector_instruction = st.session_state.stage_manager.get_stage_detector_instruction()
    
    detector_instruction = st.text_area(
        "Промпт:",
        value=current_detector_instruction,
        height=600,
        key="detector_instruction_editor"
    )
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("💾 Сохранить", type="primary", use_container_width=True):
            if detector_instruction != current_detector_instruction:
                result = st.session_state.stage_manager.save_stage_detector_instruction(detector_instruction)
                if result:
                    st.success("Промпт сохранён!")
                    
                    # Обновляем в Yandex Cloud
                    if st.session_state.langgraph_service:
                        try:
                            assistants = list(st.session_state.langgraph_service.assistants.list())
                            for assistant in assistants:
                                try:
                                    if hasattr(assistant, 'name') and assistant.name == "Определитель стадий диалога":
                                        assistant.update(instruction=detector_instruction)
                                        st.success("✅ Обновлён в Yandex Cloud!")
                                        break
                                except Exception:
                                    continue
                        except Exception as e:
                            st.warning(f"Не удалось обновить в Yandex Cloud: {e}")
                    
                    st.rerun()
                else:
                    st.error("Ошибка при сохранении")
            else:
                st.info("Промпт не изменён")
    
    with col2:
        if st.button("🔄 Сбросить", use_container_width=True):
            st.rerun()

elif st.session_state.get('current_view') == 'create' or st.session_state.get('show_create_form'):
    # Создание новой стадии
    st.header("➕ Создание новой стадии")
    
    with st.form("create_stage_form"):
        stage_name = st.text_input("Название стадии", placeholder="Агент консультации")
        stage_key = st.text_input("Ключ стадии", placeholder="consultation", help="Используется для имени файла. Это же будет название стадии в определителе.")
        instruction = st.text_area("Промпт стадии", height=300, placeholder="Введите промпт для стадии...")
        
        st.divider()
        st.markdown("**Инструкция для определителя стадий:**")
        st.markdown("Эта инструкция будет добавлена в промпт StageDetectorAgent после ключа стадии.")
        stage_detection_instruction = st.text_area(
            "Инструкция:",
            height=150,
            placeholder="- Пользователь хочет получить консультацию\n- Пользователь спрашивает о рекомендациях",
            help="Опишите, когда определять эту стадию. Каждая строка - отдельный пункт."
        )
        
        st.divider()
        available_tools = st.session_state.stage_manager.get_available_tools()
        selected_tools = st.multiselect("Инструменты:", options=available_tools)
        
        col1, col2 = st.columns(2)
        with col1:
            create_btn = st.form_submit_button("✅ Создать", type="primary", use_container_width=True)
        with col2:
            cancel_btn = st.form_submit_button("❌ Отмена", use_container_width=True)
        
        if create_btn:
            if not stage_name or not stage_key or not instruction or not stage_detection_instruction:
                st.error("Заполните все поля")
            else:
                result = st.session_state.stage_manager.create_stage(
                    stage_name=stage_name,
                    stage_key=stage_key,
                    instruction=instruction,
                    tools=selected_tools
                )
                
                if result['success']:
                    st.info("📝 Файл агента создан")
                    
                    # Добавляем стадию в определитель
                    detector_result = st.session_state.stage_manager.add_stage_to_detector(
                        stage_key=stage_key,
                        stage_name=stage_name,
                        stage_description=stage_detection_instruction
                    )
                    
                    if detector_result:
                        st.success("✅ Стадия добавлена в определитель")
                    else:
                        st.error("❌ Не удалось добавить в определитель")
                    
                    # Создаём Assistant в Yandex Cloud
                    st.info("🔧 Создание Assistant в Yandex Cloud...")
                    assistant_created = False
                    assistant_id = None
                    
                    try:
                        from src.services.langgraph_service import LangGraphService
                        
                        logger.info("=== СОЗДАНИЕ ASSISTANT В YANDEX CLOUD ===")
                        logger.info(f"stage_name: {stage_name}")
                        logger.info(f"instruction длина: {len(instruction)}")
                        logger.info(f"selected_tools: {selected_tools}")
                        
                        langgraph_service = LangGraphService()
                        logger.info("LangGraphService создан")
                        
                        tool_list = []
                        if selected_tools:
                            logger.info(f"Обработка инструментов: {selected_tools}")
                            from src.agents.tools.booking_tools import (
                                CheckAvailableSlots, CreateBooking, GetBooking,
                                CancelBooking, RescheduleBooking
                            )
                            tool_mapping = {
                                'CheckAvailableSlots': CheckAvailableSlots,
                                'CreateBooking': CreateBooking,
                                'GetBooking': GetBooking,
                                'CancelBooking': CancelBooking,
                                'RescheduleBooking': RescheduleBooking
                            }
                            tools_classes = [tool_mapping[t] for t in selected_tools if t in tool_mapping]
                            logger.info(f"Классы инструментов: {[t.__name__ for t in tools_classes]}")
                            tool_list = [langgraph_service.sdk.tools.function(t) for t in tools_classes]
                            logger.info(f"Инструменты созданы: {len(tool_list)}")
                        
                        logger.info("Вызов create_assistant...")
                        assistant = langgraph_service.create_assistant(
                            instruction=instruction,
                            tools=tool_list,
                            name=stage_name
                        )
                        assistant_id = assistant.id
                        assistant_created = True
                        logger.info(f"✅ Assistant создан: ID={assistant_id}, name={stage_name}")
                        
                        st.success(f"✅ Assistant создан (ID: {assistant_id})")
                        
                        # Проверяем сохранение в YDB
                        logger.info("Проверка сохранения в YDB...")
                        from src.ydb_client import get_ydb_client
                        ydb_client = get_ydb_client()
                        saved_id = ydb_client.get_assistant_id(stage_name)
                        if saved_id == assistant_id:
                            logger.info(f"✅ ID сохранён в YDB: {saved_id}")
                            st.success("✅ Запись добавлена в YDB")
                        else:
                            logger.warning(f"⚠️ ID не совпадает или не сохранён. Ожидалось: {assistant_id}, получено: {saved_id}")
                            st.warning("⚠️ Проблема с сохранением в YDB")
                        
                        # Обновляем определитель в Yandex Cloud
                        logger.info("Обновление определителя стадий...")
                        updated_instruction = st.session_state.stage_manager.get_stage_detector_instruction()
                        logger.info(f"Длина обновлённой инструкции: {len(updated_instruction)}")
                        
                        # Используем langgraph_service из session_state или созданный
                        service_to_use = st.session_state.langgraph_service or langgraph_service
                        if service_to_use:
                            assistants = list(service_to_use.assistants.list())
                            logger.info(f"Найдено ассистентов: {len(assistants)}")
                            detector_updated = False
                            for assistant_item in assistants:
                                try:
                                    if hasattr(assistant_item, 'name') and assistant_item.name == "Определитель стадий диалога":
                                        logger.info(f"Найден определитель стадий: {assistant_item.id}")
                                        assistant_item.update(instruction=updated_instruction)
                                        logger.info("✅ Определитель стадий обновлён")
                                        detector_updated = True
                                        st.success("✅ Определитель стадий обновлён в Yandex Cloud")
                                        break
                                except Exception as e:
                                    logger.warning(f"Ошибка при обновлении ассистента {assistant_item.id}: {e}")
                                    continue
                            if not detector_updated:
                                logger.warning("⚠️ Определитель стадий не найден для обновления")
                                st.warning("⚠️ Не удалось обновить определитель стадий")
                        else:
                            logger.error("❌ LangGraphService недоступен для обновления определителя")
                            st.error("❌ Не удалось обновить определитель стадий (сервис недоступен)")
                            
                    except Exception as e:
                        import traceback
                        error_details = traceback.format_exc()
                        logger.error(f"❌ ОШИБКА при создании Assistant: {e}")
                        logger.error(f"Детали ошибки:\n{error_details}")
                        st.error(f"❌ Ошибка создания Assistant: {e}")
                        st.code(error_details, language='python')
                    
                    if result.get('graph_added'):
                        st.success("✅ Стадия добавлена в граф")
                    else:
                        st.error("❌ Не удалось добавить в граф. Проверьте консоль для деталей.")
                    
                    if result.get('stages_added'):
                        st.success("✅ Стадия добавлена в dialogue_stages.py")
                    else:
                        st.error("❌ Не удалось добавить в dialogue_stages.py. Проверьте консоль для деталей.")
                    
                    if assistant_created:
                        st.success(f"✅ Стадия '{stage_name}' полностью создана!")
                    else:
                        st.warning(f"⚠️ Стадия '{stage_name}' создана частично. Проверьте логи.")
                    
                    st.session_state.current_view = None
                    st.session_state.show_create_form = False
                    st.rerun()
                else:
                    st.error(f"Ошибка: {result.get('error')}")
        
        if cancel_btn:
            st.session_state.current_view = None
            st.session_state.show_create_form = False
            st.rerun()

elif isinstance(st.session_state.get('current_view'), int) and 0 <= st.session_state.current_view < len(stages):
    # Редактирование стадии
    stage = stages[st.session_state.current_view]
    
    # Проверка на удаление
    if st.session_state.get('show_delete_confirm'):
        st.header("🗑️ Удаление стадии")
        st.warning(f"Удалить стадию '{stage['name']}'?")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Да, удалить", type="primary", use_container_width=True):
                result = st.session_state.stage_manager.delete_stage(stage['file_path'])
                
                if result['success']:
                    # Получаем ID из YDB
                    assistant_id = None
                    if st.session_state.ydb_client:
                        try:
                            query = "SELECT assistant_id FROM assistants WHERE assistant_name = $name"
                            db_result = st.session_state.ydb_client._execute_query(query, {"$name": stage['name']})
                            if db_result and db_result[0].rows:
                                assistant_id = db_result[0].rows[0].assistant_id.decode()
                        except Exception:
                            pass
                    
                    # Удаляем из Yandex Cloud
                    if st.session_state.langgraph_service and assistant_id:
                        try:
                            assistant = st.session_state.langgraph_service.assistants.get(assistant_id)
                            assistant.delete()
                            st.success("✅ Удалён из Yandex Cloud")
                        except Exception:
                            # Пробуем по имени
                            try:
                                assistants = list(st.session_state.langgraph_service.assistants.list())
                                for assistant in assistants:
                                    try:
                                        if hasattr(assistant, 'name') and assistant.name == stage['name']:
                                            assistant.delete()
                                            st.success("✅ Удалён из Yandex Cloud")
                                            break
                                    except Exception:
                                        continue
                            except Exception:
                                pass
                    
                    # Удаляем из YDB
                    if st.session_state.ydb_client:
                        try:
                            delete_query = """
                            DECLARE $name AS String;
                            DELETE FROM assistants WHERE assistant_name = $name;
                            """
                            st.session_state.ydb_client._execute_query(delete_query, {"$name": stage['name']})
                            st.success("✅ Удалён из YDB")
                        except Exception as e:
                            st.warning(f"⚠️ Ошибка удаления из YDB: {e}")
                    
                    # Удаляем из определителя
                    if result.get('stage_info'):
                        stage_info = result['stage_info']
                        # Используем ключ стадии из имени файла
                        stage_key_from_file = stage_info.get('stage', '')
                        st.session_state.stage_manager.remove_stage_from_detector(
                            stage_key=stage_key_from_file,
                            stage_name=stage_info.get('name', '')
                        )
                        
                        # Обновляем определитель в Yandex Cloud
                        if st.session_state.langgraph_service:
                            try:
                                updated_instruction = st.session_state.stage_manager.get_stage_detector_instruction()
                                assistants = list(st.session_state.langgraph_service.assistants.list())
                                for assistant in assistants:
                                    try:
                                        if hasattr(assistant, 'name') and assistant.name == "Определитель стадий диалога":
                                            assistant.update(instruction=updated_instruction)
                                            break
                                    except Exception:
                                        continue
                            except Exception:
                                pass
                    
                    # Удаляем из графа и dialogue_stages
                    if result.get('stage_info'):
                        stage_info = result['stage_info']
                        graph_result = st.session_state.stage_manager._remove_from_graph(
                            stage_info.get('class_name', ''),
                            stage_info.get('stage', '')
                        )
                        if graph_result:
                            st.success("✅ Удалена из графа")
                        
                        if result.get('stages_removed'):
                            st.success("✅ Удалена из dialogue_stages.py")
                        
                        if not graph_result or not result.get('stages_removed'):
                            st.warning("⚠️ Не удалось удалить из некоторых файлов автоматически")
                    
                    st.success("Стадия удалена!")
                    st.session_state.current_view = None
                    st.session_state.show_delete_confirm = False
                    st.rerun()
        
        with col2:
            if st.button("❌ Отмена", use_container_width=True):
                st.session_state.show_delete_confirm = False
                st.rerun()
    
    else:
        # Редактирование стадии
        st.header(f"📝 {stage['name']}")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.caption(f"**Файл:** `{stage['file_path']}`")
        with col2:
            st.caption(f"**Класс:** `{stage['class_name']}`")
        with col3:
            st.caption(f"**Стадия:** `{stage['stage']}`")
        
        if stage['tools']:
            st.caption(f"**Инструменты:** {', '.join(stage['tools'])}")
        
        st.divider()
        
        current_instruction = stage['instruction']
        new_instruction = st.text_area(
            "Промпт:",
            value=current_instruction,
            height=500,
            key=f"instruction_{st.session_state.current_view}"
        )
        
        col1, col2, col3 = st.columns([1, 1, 3])
        with col1:
            if st.button("💾 Сохранить", type="primary", use_container_width=True):
                if new_instruction != current_instruction:
                    result = st.session_state.stage_manager.save_stage_instruction(
                        stage['file_path'],
                        new_instruction
                    )
                    if result:
                        st.success("Сохранено!")
                        
                        # Обновляем в Yandex Cloud
                        if st.session_state.langgraph_service:
                            try:
                                assistants = list(st.session_state.langgraph_service.assistants.list())
                                for assistant in assistants:
                                    try:
                                        if hasattr(assistant, 'name') and assistant.name == stage['name']:
                                            assistant.update(instruction=new_instruction)
                                            st.success("✅ Обновлён в Yandex Cloud")
                                            break
                                    except Exception:
                                        continue
                            except Exception:
                                pass
                        
                        st.rerun()
                    else:
                        st.error("Ошибка")
                else:
                    st.info("Не изменено")
        
        with col2:
            if st.button("🗑️ Удалить", use_container_width=True):
                st.session_state.show_delete_confirm = True
                st.rerun()
        
        with col3:
            if st.button("🔄 Сбросить", use_container_width=True):
                st.rerun()

else:
    # Начальный экран
    st.info("👈 Выберите стадию в боковой панели")
