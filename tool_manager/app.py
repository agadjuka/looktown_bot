"""
Streamlit приложение для управления и тестирования инструментов
"""
import streamlit as st
import json
from typing import Dict, Any
from pathlib import Path
import sys

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tool_manager.tool_loader import ToolLoader, create_mock_thread


def init_session_state():
    """Инициализация состояния сессии"""
    if 'tool_loader' not in st.session_state:
        st.session_state.tool_loader = ToolLoader()
        with st.spinner("Загрузка инструментов..."):
            st.session_state.tool_loader.load_all_tools()
        
        # Показываем ошибки загрузки, если есть
        if hasattr(st.session_state.tool_loader, 'errors') and st.session_state.tool_loader.errors:
            with st.sidebar.expander("⚠️ Ошибки загрузки", expanded=True):
                for error in st.session_state.tool_loader.errors:
                    st.error(error)
    
    if 'selected_tool' not in st.session_state:
        tool_names = st.session_state.tool_loader.get_all_tool_names()
        st.session_state.selected_tool = tool_names[0] if tool_names else None
    
    if 'test_results' not in st.session_state:
        st.session_state.test_results = {}


def render_tool_list():
    """Отображает список инструментов в боковой панели"""
    st.sidebar.title("🔧 Инструменты")
    
    tool_names = st.session_state.tool_loader.get_all_tool_names()
    
    if not tool_names:
        st.sidebar.warning("Инструменты не найдены")
        
        # Показываем отладочную информацию
        with st.sidebar.expander("🔍 Отладка", expanded=False):
            st.text(f"Загружено инструментов: {len(st.session_state.tool_loader.tools)}")
            if hasattr(st.session_state.tool_loader, 'errors'):
                st.text(f"Ошибок: {len(st.session_state.tool_loader.errors)}")
            st.text(f"Путь к tools: {st.session_state.tool_loader.tools_dir}")
        
        return
    
    # Выбор инструмента
    selected = st.sidebar.selectbox(
        "Выберите инструмент:",
        tool_names,
        index=tool_names.index(st.session_state.selected_tool) if st.session_state.selected_tool in tool_names else 0
    )
    
    st.session_state.selected_tool = selected
    
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Всего инструментов:** {len(tool_names)}")
    
    # Кнопка перезагрузки инструментов
    if st.sidebar.button("🔄 Перезагрузить инструменты"):
        st.session_state.tool_loader = ToolLoader()
        with st.spinner("Загрузка инструментов..."):
            st.session_state.tool_loader.load_all_tools()
        st.rerun()


def render_tool_info():
    """Отображает информацию о выбранном инструменте"""
    if not st.session_state.selected_tool:
        st.warning("Выберите инструмент из списка")
        return
    
    tool_info = st.session_state.tool_loader.get_tool(st.session_state.selected_tool)
    
    if not tool_info:
        st.error(f"Инструмент '{st.session_state.selected_tool}' не найден")
        return
    
    # Заголовок
    st.title(f"🔧 {tool_info.name}")
    
    # Описание инструмента
    st.header("📝 Описание")
    description = tool_info.get_full_description()
    st.markdown(f"```\n{description}\n```")
    
    st.markdown("---")
    
    # Параметры инструмента
    st.header("⚙️ Параметры")
    
    if tool_info.parameters:
        params_data = []
        for param in tool_info.parameters:
            required_mark = "✅ Обязательный" if param['required'] else "⚪ Опциональный"
            default_value = f" (по умолчанию: {param['default']})" if param['default'] is not None else ""
            params_data.append({
                "Параметр": param['name'],
                "Тип": param['type'],
                "Обязательность": required_mark,
                "Описание": param['description'] + default_value
            })
        
        st.dataframe(params_data, use_container_width=True, hide_index=True)
    else:
        st.info("Этот инструмент не требует параметров")
    
    st.markdown("---")
    
    # JSON схема инструмента
    st.header("📋 JSON Схема")
    with st.expander("Показать JSON схему инструмента"):
        try:
            schema = tool_info.tool_class.model_json_schema()
            st.json(schema)
        except Exception as e:
            st.error(f"Ошибка при получении схемы: {e}")
    
    st.markdown("---")
    
    # Тестирование инструмента
    st.header("🧪 Тестирование")
    
    # Форма для ввода параметров
    with st.form("test_tool_form"):
        form_params = {}
        
        if tool_info.parameters:
            st.subheader("Введите параметры:")
            for param in tool_info.parameters:
                param_name = param['name']
                param_type = param['type']
                param_desc = param['description']
                param_required = param['required']
                param_default = param['default']
                
                # Определяем тип ввода
                if param_type == 'integer':
                    value = st.number_input(
                        f"{param_name} ({'обязательный' if param_required else 'опциональный'})",
                        help=param_desc,
                        value=int(param_default) if param_default is not None else None,
                        step=1,
                        key=f"param_{param_name}"
                    )
                    if value is not None:
                        form_params[param_name] = int(value)
                elif param_type == 'number':
                    value = st.number_input(
                        f"{param_name} ({'обязательный' if param_required else 'опциональный'})",
                        help=param_desc,
                        value=float(param_default) if param_default is not None else None,
                        step=0.1,
                        key=f"param_{param_name}"
                    )
                    if value is not None:
                        form_params[param_name] = float(value)
                elif param_type == 'boolean':
                    value = st.checkbox(
                        f"{param_name} ({'обязательный' if param_required else 'опциональный'})",
                        help=param_desc,
                        value=param_default if param_default is not None else False,
                        key=f"param_{param_name}"
                    )
                    form_params[param_name] = value
                else:  # string и другие
                    value = st.text_input(
                        f"{param_name} ({'обязательный' if param_required else 'опциональный'})",
                        help=param_desc,
                        value=str(param_default) if param_default is not None else "",
                        key=f"param_{param_name}"
                    )
                    # Добавляем параметр только если он заполнен или обязателен
                    if value:
                        form_params[param_name] = value
                    elif param_required:
                        # Для обязательных параметров добавляем пустую строку, чтобы валидация сработала
                        form_params[param_name] = ""
        
        submitted = st.form_submit_button("🚀 Запустить тест", use_container_width=True)
        
        if submitted:
            # Проверяем обязательные параметры
            missing_required = []
            for param in tool_info.parameters:
                if param['required']:
                    param_name = param['name']
                    if param_name not in form_params or form_params[param_name] == "" or form_params[param_name] is None:
                        missing_required.append(param_name)
            
            if missing_required:
                st.error(f"❌ Не заполнены обязательные параметры: {', '.join(missing_required)}")
            else:
                # Удаляем пустые значения для опциональных параметров
                cleaned_params = {k: v for k, v in form_params.items() if v != "" and v is not None}
                
                # Выполняем тест
                with st.spinner("Выполнение инструмента..."):
                    try:
                        # Создаем экземпляр инструмента
                        if cleaned_params:
                            tool_instance = tool_info.tool_class(**cleaned_params)
                        else:
                            tool_instance = tool_info.tool_class()
                        
                        # Создаем mock thread
                        thread = create_mock_thread()
                        
                        # Выполняем процесс
                        result = tool_instance.process(thread)
                        
                        # Сохраняем результат
                        test_key = f"{tool_info.name}_{len(st.session_state.test_results)}"
                        st.session_state.test_results[test_key] = {
                            'tool_name': tool_info.name,
                            'parameters': cleaned_params.copy(),
                            'result': result,
                            'success': True
                        }
                        
                        st.success("✅ Инструмент выполнен успешно!")
                        st.rerun()
                        
                    except Exception as e:
                        import traceback
                        error_msg = str(e)
                        error_traceback = traceback.format_exc()
                        st.error(f"❌ Ошибка при выполнении инструмента: {error_msg}")
                        with st.expander("Детали ошибки"):
                            st.code(error_traceback)
                        
                        # Сохраняем ошибку
                        test_key = f"{tool_info.name}_{len(st.session_state.test_results)}"
                        st.session_state.test_results[test_key] = {
                            'tool_name': tool_info.name,
                            'parameters': cleaned_params.copy(),
                            'result': None,
                            'error': error_msg,
                            'error_traceback': error_traceback,
                            'success': False
                        }
    
    # Показываем результаты тестирования
    if st.session_state.test_results:
        st.markdown("---")
        st.header("📊 История тестов")
        
        # Фильтруем результаты для текущего инструмента
        tool_results = {
            k: v for k, v in st.session_state.test_results.items()
            if v['tool_name'] == tool_info.name
        }
        
        if tool_results:
            # Показываем последний результат
            last_result_key = list(tool_results.keys())[-1]
            last_result = tool_results[last_result_key]
            
            st.subheader("Последний результат:")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Статус", "✅ Успешно" if last_result['success'] else "❌ Ошибка")
            
            with col2:
                st.metric("Параметры", len(last_result['parameters']))
            
            st.subheader("Входные параметры:")
            st.json(last_result['parameters'])
            
            st.subheader("Результат выполнения:")
            if last_result['success']:
                st.code(last_result['result'], language=None)
            else:
                st.error(last_result.get('error', 'Неизвестная ошибка'))
            
            # Кнопка очистки истории
            if st.button("🗑️ Очистить историю тестов"):
                st.session_state.test_results = {}
                st.rerun()


def main():
    """Главная функция приложения"""
    st.set_page_config(
        page_title="Tool Manager",
        page_icon="🔧",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    init_session_state()
    
    # Боковая панель со списком инструментов
    render_tool_list()
    
    # Основная область с информацией об инструменте
    render_tool_info()


if __name__ == "__main__":
    main()

