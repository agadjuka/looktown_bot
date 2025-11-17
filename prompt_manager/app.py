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
    st.session_state.current_view = None  # 'detector' или индекс стадии

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
    
    st.markdown("**Промпт определителя стадий (редактируемый):**")
    
    detector_template = st.text_area(
        "Промпт:",
        value=current_detector_instruction,
        height=400,
        key="detector_template_editor",
        help="Полный промпт для определителя стадий. Включает список всех стадий с описаниями."
    )
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("💾 Сохранить промпт", type="primary", use_container_width=True):
            if detector_template != current_detector_instruction:
                result = st.session_state.stage_manager.save_stage_detector_instruction(detector_template)
                if result:
                    st.success("✅ Изменения относили")
                    st.rerun()
                else:
                    st.error("❌ Ошибка сохранения")
            else:
                st.info("Промпт не изменён")
    
    with col2:
        if st.button("🔄 Сбросить", use_container_width=True):
            st.rerun()
    
    st.divider()
    
    # Управление описаниями стадий (для удобства редактирования отдельных стадий)
    st.markdown("**Быстрое редактирование описаний стадий:**")
    st.markdown("*Можно редактировать описания отдельных стадий, они будут обновлены в промпте*")
    
    try:
        # Парсим файл dialogue_stages.py напрямую, без импорта
        dialogue_stages_file = st.session_state.stage_manager.dialogue_stages_file
        stage_keys = []
        
        if dialogue_stages_file.exists():
            with open(dialogue_stages_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Ищем все значения стадий в формате: STAGE_NAME = "stage_key"
            import re
            pattern = r'\s+(\w+)\s*=\s*"([^"]+)"'
            matches = re.findall(pattern, content)
            for enum_name, stage_key in matches:
                stage_keys.append(stage_key)
        
        # Извлекаем описания из текущего промпта
        descriptions = {}
        if current_detector_instruction:
            for line in current_detector_instruction.split('\n'):
                if line.strip().startswith('- ') and ':' in line:
                    parts = line.strip()[2:].split(':', 1)
                    if len(parts) == 2:
                        stage_key = parts[0].strip()
                        description = parts[1].strip()
                        descriptions[stage_key] = description
        
        # Если не нашли стадии в файле, используем те, что есть в описаниях
        if not stage_keys:
            stage_keys = list(descriptions.keys())
        
        for stage_key in sorted(set(stage_keys)):
            current_desc = descriptions.get(stage_key, "")
            
            with st.expander(f"📝 {stage_key}", expanded=False):
                new_desc = st.text_area(
                    f"Описание для '{stage_key}':",
                    value=current_desc,
                    height=100,
                    key=f"desc_{stage_key}",
                    help="Краткое описание стадии для определителя"
                )
                
                if st.button(f"💾 Сохранить описание", key=f"save_desc_{stage_key}"):
                    if new_desc != current_desc:
                        # Обновляем описание в промпте
                        result = st.session_state.stage_manager.add_stage_to_detector(stage_key, stage_key, new_desc)
                        if result:
                            st.success("✅ Изменения относили")
                            st.rerun()
                        else:
                            st.error("❌ Ошибка сохранения описания")
    except Exception as e:
        logger.error(f"Ошибка загрузки описаний стадий: {e}")
        st.error(f"❌ Ошибка: {e}")

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
                    
                    if result.get('graph_added'):
                        st.success("✅ Стадия добавлена в граф")
                    else:
                        st.error("❌ Не удалось добавить в граф. Проверьте консоль для деталей.")
                    
                    if result.get('stages_added'):
                        st.success("✅ Стадия добавлена в dialogue_stages.py")
                    else:
                        st.error("❌ Не удалось добавить в dialogue_stages.py. Проверьте консоль для деталей.")
                    
                    st.success(f"✅ Стадия '{stage_name}' создана!")
                    
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
                    # Удаляем из определителя
                    if result.get('stage_info'):
                        stage_info = result['stage_info']
                        # Используем ключ стадии из имени файла
                        stage_key_from_file = stage_info.get('stage', '')
                        st.session_state.stage_manager.remove_stage_from_detector(
                            stage_key=stage_key_from_file,
                            stage_name=stage_info.get('name', '')
                        )
                    
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
                    
                    st.success("✅ Изменения относили")
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
        
        # Управление инструментами
        st.markdown("**🔧 Управление инструментами:**")
        available_tools = st.session_state.stage_manager.get_available_tools()
        current_tools = stage.get('tools', [])
        
        # Создаём галочки для каждого инструмента и собираем выбранные
        selected_tools = []
        cols = st.columns(3)
        for i, tool in enumerate(available_tools):
            col_idx = i % 3
            with cols[col_idx]:
                checked = tool in current_tools
                tool_key = f"tool_{st.session_state.current_view}_{tool}"
                # Инициализируем значение в session_state если его нет
                if tool_key not in st.session_state:
                    st.session_state[tool_key] = checked
                # Создаём checkbox
                is_checked = st.checkbox(tool, value=st.session_state[tool_key], key=tool_key)
                if is_checked:
                    selected_tools.append(tool)
        
        st.divider()
        
        # Редактирование описания для определителя стадий
        st.markdown("**Описание для определителя стадий:**")
        try:
            # Извлекаем описание из текущего промпта определителя
            detector_instruction = st.session_state.stage_manager.get_stage_detector_instruction()
            current_stage_desc = ""
            if detector_instruction:
                for line in detector_instruction.split('\n'):
                    if line.strip().startswith(f"- {stage['stage']}:"):
                        parts = line.strip()[2:].split(':', 1)
                        if len(parts) == 2:
                            current_stage_desc = parts[1].strip()
                            break
        except Exception:
            current_stage_desc = ""
        
        new_stage_desc = st.text_area(
            "Описание стадии:",
            value=current_stage_desc,
            height=100,
            key=f"stage_desc_{st.session_state.current_view}",
            help="Краткое описание стадии для определителя стадий"
        )
        
        st.divider()
        
        current_instruction = stage['instruction']
        new_instruction = st.text_area(
            "Промпт стадии:",
            value=current_instruction,
            height=500,
            key=f"instruction_{st.session_state.current_view}"
        )
        
        col1, col2, col3 = st.columns([1, 1, 3])
        with col1:
            if st.button("💾 Сохранить", type="primary", use_container_width=True):
                changes_made = False
                
                # Сохраняем описание стадии для определителя
                if new_stage_desc != current_stage_desc:
                    try:
                        result = st.session_state.stage_manager.add_stage_to_detector(
                            stage['stage'], 
                            stage['name'], 
                            new_stage_desc
                        )
                        if result:
                            st.success("✅ Изменения относили")
                            changes_made = True
                        else:
                            st.error("❌ Ошибка сохранения описания")
                    except Exception as e:
                        logger.error(f"Ошибка сохранения описания стадии: {e}")
                        st.error(f"❌ Ошибка сохранения описания: {e}")
                
                # Сохраняем инструменты
                if set(selected_tools) != set(current_tools):
                    tools_result = st.session_state.stage_manager.update_stage_tools(
                        stage['file_path'],
                        selected_tools
                    )
                    if tools_result:
                        st.success("✅ Изменения относили")
                        changes_made = True
                    else:
                        st.error("❌ Ошибка обновления инструментов")
                
                # Сохраняем промпт стадии
                if new_instruction != current_instruction:
                    result = st.session_state.stage_manager.save_stage_instruction(
                        stage['file_path'],
                        new_instruction
                    )
                    if result:
                        st.success("✅ Изменения относили")
                        changes_made = True
                    else:
                        st.error("❌ Ошибка сохранения промпта")
                
                if changes_made:
                    st.rerun()
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
