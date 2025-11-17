"""
Менеджер стадий - логика работы со стадиями (агентами)
"""
import os
import re
import ast
from typing import List, Dict, Optional
from pathlib import Path
import importlib.util
import sys
import inspect
from pydantic import BaseModel

class StageManager:
    """Менеджер для работы со стадиями (агентами)"""
    
    def __init__(self, project_root: str = None):
        if project_root is None:
            # Определяем корень проекта (на уровень выше prompt_manager)
            self.project_root = Path(__file__).parent.parent
        else:
            self.project_root = Path(project_root)
        
        self.agents_dir = self.project_root / "src" / "agents"
        self.graph_file = self.project_root / "src" / "graph" / "main_graph.py"
        self.dialogue_stages_file = self.project_root / "src" / "agents" / "dialogue_stages.py"
        self.stage_detector_file = self.project_root / "src" / "agents" / "stage_detector_agent.py"
    
    def get_all_stages(self) -> List[Dict]:
        """Получить все стадии (агенты)"""
        stages = []
        
        # Исключаем служебные файлы
        excluded = {'__init__.py', 'base_agent.py', 'dialogue_stages.py', 'stage_detector_agent.py', 'tools'}
        
        if not self.agents_dir.exists():
            return stages
        
        for file_path in self.agents_dir.iterdir():
            if file_path.is_file() and file_path.suffix == '.py' and file_path.name not in excluded:
                stage_info = self._parse_agent_file(file_path)
                if stage_info:
                    stages.append(stage_info)
        
        return sorted(stages, key=lambda x: x['name'])
    
    def _parse_agent_file(self, file_path: Path) -> Optional[Dict]:
        """Парсинг файла агента для извлечения информации"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Извлекаем имя класса
            class_match = re.search(r'class\s+(\w+Agent)', content)
            if not class_match:
                return None
            
            class_name = class_match.group(1)
            
            # Извлекаем промпт (instruction)
            instruction_match = re.search(r'instruction\s*=\s*"""(.*?)"""', content, re.DOTALL)
            if not instruction_match:
                # Пробуем найти в тройных кавычках
                instruction_match = re.search(r'instruction\s*=\s*"""(.*?)"""', content, re.DOTALL | re.MULTILINE)
            
            instruction = instruction_match.group(1).strip() if instruction_match else ""
            
            # Извлекаем agent_name
            agent_name_match = re.search(r'agent_name\s*=\s*["\']([^"\']+)["\']', content)
            agent_name = agent_name_match.group(1) if agent_name_match else class_name
            
            # Определяем используемые инструменты (динамически)
            available_tools = self.get_available_tools()
            tools = []
            for tool_name in available_tools:
                if tool_name in content:
                    tools.append(tool_name)
            
            # Определяем стадию из имени файла (ключ стадии)
            stage = self._extract_stage_from_file(file_path)
            # Если не получилось, пробуем из класса
            if stage == file_path.stem:
                stage = self._extract_stage_from_name(class_name)
            
            return {
                'file_path': str(file_path.relative_to(self.project_root)),
                'class_name': class_name,
                'name': agent_name,
                'stage': stage,
                'instruction': instruction,
                'tools': tools,
                'full_path': str(file_path)
            }
        except Exception as e:
            print(f"Ошибка при парсинге {file_path}: {e}")
            return None
    
    def _extract_stage_from_name(self, class_name: str) -> str:
        """Извлечь название стадии из имени класса или файла"""
        mapping = {
            'GreetingAgent': 'greeting',
            'BookingAgent': 'booking',
            'CancelBookingAgent': 'cancel_booking',
            'RescheduleAgent': 'reschedule',
        }
        
        # Если не нашлось в маппинге, пробуем извлечь из имени файла
        if class_name not in mapping:
            # Имя файла вида "consultation_agent.py" -> "consultation"
            return 'unknown'
        
        return mapping.get(class_name, 'unknown')
    
    def _extract_stage_from_file(self, file_path: Path) -> str:
        """Извлечь ключ стадии из имени файла"""
        # Имя файла вида "consultation_agent.py" -> "consultation"
        file_name = file_path.stem  # без расширения
        if file_name.endswith('_agent'):
            return file_name[:-6]  # убираем "_agent"
        return file_name
    
    def get_stage_instruction(self, file_path: str) -> str:
        """Получить промпт стадии"""
        full_path = self.project_root / file_path
        if not full_path.exists():
            return ""
        
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        instruction_match = re.search(r'instruction\s*=\s*"""(.*?)"""', content, re.DOTALL)
        if instruction_match:
            return instruction_match.group(1).strip()
        return ""
    
    def save_stage_instruction(self, file_path: str, new_instruction: str) -> bool:
        """Сохранить промпт стадии"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            full_path = self.project_root / file_path
            if not full_path.exists():
                logger.error(f"Файл не найден: {full_path}")
                return False
            
            # Сохраняем резервную копию на случай ошибки
            backup_content = None
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    backup_content = f.read()
            except Exception as e:
                logger.warning(f"Не удалось создать резервную копию: {e}")
            
            # Используем regex для замены промпта - более надежный метод
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Очищаем возможные проблемы с лишними кавычками в исходном файле
            # Убираем четыре и более кавычек подряд, заменяя на три
            content = re.sub(r'""""+', '"""', content)
            
            # Паттерн для поиска instruction = """..."""
            # Используем non-greedy match с учетом многострочности
            pattern = r'(instruction\s*=\s*""")' + r'(.*?)' + r'(""")'
            
            # Проверяем, есть ли совпадение
            match = re.search(pattern, content, re.DOTALL)
            if not match:
                logger.error("Не найдено поле instruction в файле")
                return False
            
            # Заменяем содержимое между тройными кавычками
            # Важно: new_instruction может содержать тройные кавычки, которые нужно экранировать
            # Заменяем тройные кавычки внутри промпта на временный маркер, чтобы не сломать синтаксис
            # Используем маркер, который точно не встретится в промпте
            TEMP_TRIPLE_QUOTE_MARKER = "___TRIPLE_QUOTE_REPLACEMENT___"
            escaped_instruction = new_instruction.replace('"""', TEMP_TRIPLE_QUOTE_MARKER)
            
            # Убираем возможные лишние кавычки в конце escaped_instruction
            # Это важно, чтобы избежать ситуации, когда в конце промпта есть " и затем идет """
            # что создаст """" (четыре кавычки подряд)
            escaped_instruction = escaped_instruction.rstrip('"')
            
            new_content = content[:match.start(2)] + escaped_instruction + content[match.end(2):]
            
            # Теперь заменяем временный маркер обратно на тройные одинарные кавычки
            # Внутри тройных двойных кавычек можно использовать тройные одинарные кавычки
            final_content = new_content.replace(TEMP_TRIPLE_QUOTE_MARKER, "'''")
            
            # Дополнительная проверка: убираем возможные лишние кавычки перед закрывающими тройными кавычками
            # Ищем паттерн """ перед закрывающими """ и заменяем четыре и более кавычек на три
            final_content = re.sub(r'""""+', '"""', final_content)
            
            # Сохраняем файл
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            # Проверяем синтаксис Python после сохранения
            try:
                ast.parse(final_content)
            except SyntaxError as e:
                logger.error(f"Синтаксическая ошибка после сохранения: {e}")
                logger.error(f"Ошибка на строке {e.lineno}, позиция {e.offset}")
                # Выводим контекст вокруг ошибки
                lines = final_content.split('\n')
                error_line_idx = e.lineno - 1 if e.lineno else 0
                start_idx = max(0, error_line_idx - 3)
                end_idx = min(len(lines), error_line_idx + 4)
                context = '\n'.join(lines[start_idx:end_idx])
                logger.error(f"Контекст ошибки (строки {start_idx+1}-{end_idx}):\n{context}")
                # Восстанавливаем из резервной копии
                if backup_content:
                    try:
                        with open(full_path, 'w', encoding='utf-8') as f:
                            f.write(backup_content)
                        logger.info("Файл восстановлен из резервной копии")
                    except Exception as restore_error:
                        logger.error(f"Не удалось восстановить файл: {restore_error}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении: {e}", exc_info=True)
            # Пробуем восстановить из резервной копии
            if backup_content:
                try:
                    full_path = self.project_root / file_path
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write(backup_content)
                    logger.info("Файл восстановлен из резервной копии после исключения")
                except Exception:
                    pass
            return False
    
    def create_stage(self, stage_name: str, stage_key: str, instruction: str, tools: List[str] = None) -> Dict:
        """Создать новую стадию"""
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"=== НАЧАЛО СОЗДАНИЯ СТАДИИ ===")
        logger.info(f"stage_name: {stage_name}")
        logger.info(f"stage_key: {stage_key}")
        logger.info(f"instruction длина: {len(instruction)}")
        logger.info(f"tools: {tools}")
        
        if tools is None:
            tools = []
        
        # Генерируем имя класса
        class_name = f"{''.join(word.capitalize() for word in stage_key.split('_'))}Agent"
        file_name = f"{stage_key}_agent.py"
        file_path = self.agents_dir / file_name
        
        logger.info(f"class_name: {class_name}")
        logger.info(f"file_name: {file_name}")
        logger.info(f"file_path: {file_path}")
        
        if file_path.exists():
            logger.error(f"Файл {file_name} уже существует!")
            return {'success': False, 'error': f'Файл {file_name} уже существует'}
        
        # Создаём содержимое файла
        # Определяем модуль для каждого инструмента
        tool_module_mapping = self._get_tool_module_mapping()
        available_tools = self.get_available_tools()
        
        # Группируем инструменты по модулям
        tools_by_module = {}
        for tool_name in tools:
            if tool_name in available_tools:
                module = tool_module_mapping.get(tool_name, 'service_tools')
                if module not in tools_by_module:
                    tools_by_module[module] = []
                tools_by_module[module].append(tool_name)
        
        # Формируем импорты
        imports = ""
        tools_list = []
        for module, module_tools in sorted(tools_by_module.items()):
            if module_tools:
                imports += f"from .tools.{module} import {', '.join(sorted(module_tools))}\n"
                tools_list.extend(module_tools)
        
        tools_param = "None"
        if tools_list:
            # Формируем список инструментов с кавычками
            quoted_tools = ['"' + tool + '"' for tool in sorted(tools_list)]
            tools_param = f"[{', '.join(quoted_tools)}]"
        
        # Экранируем тройные кавычки в instruction, заменяя их на тройные одинарные
        # чтобы не сломать синтаксис Python
        escaped_instruction = instruction.replace('"""', "'''")
        
        file_content = f'''"""
Агент для стадии {stage_name}
"""
{imports}from .base_agent import BaseAgent
from ..services.langgraph_service import LangGraphService


class {class_name}(BaseAgent):
    """Агент для стадии {stage_name}"""
    
    def __init__(self, langgraph_service: LangGraphService):
        instruction = """{escaped_instruction}"""
        
        super().__init__(
            langgraph_service=langgraph_service,
            instruction=instruction,
            tools={tools_param},
            agent_name="{stage_name}"
        )
'''
        
        try:
            logger.info("Создание файла агента...")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(file_content)
            logger.info(f"✅ Файл создан: {file_path}")
            
            # Добавляем стадию в dialogue_stages.py
            logger.info("Добавление в dialogue_stages.py...")
            stages_result = self._add_to_dialogue_stages(stage_key, stage_name)
            logger.info(f"Результат добавления в dialogue_stages: {stages_result}")
            
            # Добавляем в граф
            logger.info("Добавление в граф...")
            graph_result = self._add_to_graph(class_name, stage_key, stage_name)
            logger.info(f"Результат добавления в граф: {graph_result}")
            
            logger.info("=== СОЗДАНИЕ СТАДИИ ЗАВЕРШЕНО ===")
            return {
                'success': True,
                'file_path': str(file_path.relative_to(self.project_root)),
                'class_name': class_name,
                'graph_added': graph_result,
                'stages_added': stages_result
            }
        except Exception as e:
            logger.error(f"❌ ОШИБКА при создании стадии: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    def delete_stage(self, file_path: str) -> Dict:
        """Удалить стадию"""
        full_path = self.project_root / file_path
        if not full_path.exists():
            return {'success': False, 'error': 'Файл не найден'}
        
        try:
            # Получаем информацию о стадии перед удалением
            stage_info = self._parse_agent_file(full_path)
            
            # Удаляем файл
            full_path.unlink()
            
            # Проверяем, что файл действительно удалён
            if full_path.exists():
                return {'success': False, 'error': 'Не удалось удалить файл'}
            
            # Удаляем из графа
            graph_removed = False
            if stage_info:
                graph_removed = self._remove_from_graph(
                    stage_info['class_name'],
                    stage_info.get('stage', '')
                )
            
            # Удаляем из dialogue_stages.py
            stages_removed = False
            if stage_info:
                stages_removed = self._remove_from_dialogue_stages(stage_info.get('stage', ''))
            
            return {
                'success': True,
                'stage_info': stage_info,
                'graph_removed': graph_removed,
                'stages_removed': stages_removed
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _remove_from_graph(self, class_name: str, stage_key: str):
        """Удалить стадию из main_graph.py"""
        if not class_name or not self.graph_file.exists():
            return False
        
        try:
            with open(self.graph_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Удаляем импорт
            import_pattern = rf'from \.\.agents\.\w+ import {re.escape(class_name)}'
            content = re.sub(import_pattern, '', content)
            
            # Удаляем из кэша агентов
            cache_pattern = rf"'{stage_key}_agent': {re.escape(class_name)}\(langgraph_service\),?\s*"
            content = re.sub(cache_pattern, '', content)
            
            # Удаляем присваивание агента
            assign_pattern = rf'self\.{stage_key}_agent = agents\[\'{stage_key}_agent\'\]\s*'
            content = re.sub(assign_pattern, '', content)
            
            # Удаляем узел из графа
            node_pattern = rf'graph\.add_node\("handle_{re.escape(stage_key)}", self\._handle_{re.escape(stage_key)}\)\s*'
            content = re.sub(node_pattern, '', content)
            
            # Удаляем маршрутизацию
            route_pattern = rf'"{re.escape(stage_key)}": "handle_{re.escape(stage_key)}",?\s*'
            content = re.sub(route_pattern, '', content)
            
            # Удаляем рёбра
            edge_pattern = rf'graph\.add_edge\("handle_{re.escape(stage_key)}", END\)\s*'
            content = re.sub(edge_pattern, '', content)
            
            # Удаляем обработчик
            handler_pattern = rf'def _handle_{re.escape(stage_key)}\(self, state: ConversationState\) -> ConversationState:.*?return.*?\n\n'
            content = re.sub(handler_pattern, '', content, flags=re.DOTALL)
            
            with open(self.graph_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return True
        except Exception as e:
            print(f"Предупреждение: не удалось удалить из графа: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _add_to_graph(self, class_name: str, stage_key: str, stage_name: str):
        """Добавить стадию в main_graph.py"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"=== ДОБАВЛЕНИЕ В ГРАФ ===")
        logger.info(f"class_name: {class_name}, stage_key: {stage_key}, stage_name: {stage_name}")
        logger.info(f"Файл существует: {self.graph_file.exists()}")
        
        if not class_name or not self.graph_file.exists():
            logger.error(f"Проверка не прошла: class_name={class_name}, файл существует={self.graph_file.exists()}")
            return False
        
        try:
            with open(self.graph_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            logger.info(f"Файл прочитан, строк: {len(lines)}")
            
            import_line = f'from ..agents.{stage_key}_agent import {class_name}\n'
            
            # Проверяем, есть ли уже импорт
            if import_line.strip() not in ''.join(lines):
                logger.info("Добавление импорта...")
                # Ищем место после последнего импорта агента
                for i in range(len(lines) - 1, -1, -1):
                    if 'from ..agents.' in lines[i] and '_agent import' in lines[i]:
                        logger.info(f"Найдено место для импорта на строке {i+1}")
                        lines.insert(i + 1, import_line)
                        break
                else:
                    logger.warning("Не найдено место для импорта")
            else:
                logger.info("Импорт уже существует")
            
            # Добавляем в кэш агентов (после greeting_agent)
            cache_line = f"                '{stage_key}_agent': {class_name}(langgraph_service),\n"
            cache_added = False
            # Проверяем, нет ли уже этого агента в кэше
            if f"'{stage_key}_agent':" not in ''.join(lines):
                for i, line in enumerate(lines):
                    if "'greeting_agent': GreetingAgent(langgraph_service)" in line:
                        logger.info(f"Найдено место для кэша на строке {i+1}")
                        lines.insert(i + 1, cache_line)
                        cache_added = True
                        break
                if not cache_added:
                    logger.warning("Не найдено место для добавления в кэш")
            else:
                logger.info("Агент уже есть в кэше")
            
            # Добавляем присваивание агента (после greeting_agent)
            assign_line = f"        self.{stage_key}_agent = agents['{stage_key}_agent']\n"
            assign_added = False
            # Проверяем, нет ли уже этого присваивания
            if f"self.{stage_key}_agent = agents" not in ''.join(lines):
                for i, line in enumerate(lines):
                    if 'self.greeting_agent = agents' in line:
                        logger.info(f"Найдено место для присваивания на строке {i+1}")
                        lines.insert(i + 1, assign_line)
                        assign_added = True
                        break
                if not assign_added:
                    logger.warning("Не найдено место для присваивания агента")
            else:
                logger.info("Присваивание агента уже существует")
            
            # Добавляем узел в граф (после handle_reschedule)
            node_line = f'        graph.add_node("handle_{stage_key}", self._handle_{stage_key})\n'
            node_added = False
            # Проверяем, нет ли уже этого узла
            if f'graph.add_node("handle_{stage_key}"' not in ''.join(lines):
                for i, line in enumerate(lines):
                    if 'graph.add_node("handle_reschedule"' in line:
                        logger.info(f"Найдено место для узла на строке {i+1}")
                        lines.insert(i + 1, node_line)
                        node_added = True
                        break
                if not node_added:
                    logger.warning("Не найдено место для добавления узла")
            else:
                logger.info("Узел уже добавлен в граф")
            
            # Добавляем маршрутизацию в conditional_edges
            route_line = f'                "{stage_key}": "handle_{stage_key}",\n'
            route_added = False
            # Проверяем, нет ли уже этой маршрутизации
            if f'"{stage_key}": "handle_{stage_key}"' not in ''.join(lines):
                for i, line in enumerate(lines):
                    if '"reschedule": "handle_reschedule",' in line:
                        logger.info(f"Найдено место для маршрутизации на строке {i+1}")
                        lines.insert(i + 1, route_line)
                        route_added = True
                        break
                if not route_added:
                    logger.warning("Не найдено место для маршрутизации")
            else:
                logger.info("Маршрутизация уже добавлена")
            
            # Добавляем рёбра (после handle_reschedule)
            edge_line = f'        graph.add_edge("handle_{stage_key}", END)\n'
            edge_added = False
            # Проверяем, нет ли уже этого ребра
            if f'graph.add_edge("handle_{stage_key}", END)' not in ''.join(lines):
                for i, line in enumerate(lines):
                    if 'graph.add_edge("handle_reschedule", END)' in line:
                        logger.info(f"Найдено место для рёбер на строке {i+1}")
                        lines.insert(i + 1, edge_line)
                        edge_added = True
                        break
                if not edge_added:
                    logger.warning("Не найдено место для добавления рёбер")
            else:
                logger.info("Рёбра уже добавлены")
            
            # Добавляем обработчик (после _handle_reschedule, перед концом класса)
            handler_code = f'''    def _handle_{stage_key}(self, state: ConversationState) -> ConversationState:
        """Обработка стадии {stage_name}"""
        logger.info("Обработка стадии {stage_key}")
        message = state["message"]
        thread = state["thread"]
        
        answer = self.{stage_key}_agent(message, thread)
        used_tools = [tool["name"] for tool in self.{stage_key}_agent._last_tool_calls] if hasattr(self.{stage_key}_agent, '_last_tool_calls') and self.{stage_key}_agent._last_tool_calls else []
        
        return {{"answer": answer, "agent_name": "{class_name}", "used_tools": used_tools}}

'''
            # Проверяем, нет ли уже этого обработчика
            handler_inserted = False
            if f'def _handle_{stage_key}(' not in ''.join(lines):
                # Ищем место после _handle_reschedule
                for i, line in enumerate(lines):
                    if 'def _handle_reschedule' in line:
                        # Ищем конец метода _handle_reschedule (пустая строка после return)
                        for j in range(i + 1, min(i + 20, len(lines))):
                            if lines[j].strip() == '' and j > i + 5:  # Пустая строка после нескольких строк кода
                                # Проверяем, что перед этим был return
                                for k in range(j - 1, max(i, j - 10), -1):
                                    if 'return {' in lines[k]:
                                        lines.insert(j + 1, handler_code)
                                        handler_inserted = True
                                        logger.info(f"Обработчик добавлен после строки {j+1}")
                                        break
                                if handler_inserted:
                                    break
                        if not handler_inserted:
                            # Если не нашли, добавляем через 10 строк после начала метода
                            lines.insert(i + 12, handler_code)
                            handler_inserted = True
                            logger.info(f"Обработчик добавлен после строки {i+12}")
                        break
                
                if not handler_inserted:
                    # Если вообще не нашли _handle_reschedule, добавляем в конец перед последней строкой
                    for i in range(len(lines) - 1, -1, -1):
                        if lines[i].strip() and not lines[i].strip().startswith('#'):
                            lines.insert(i + 1, handler_code)
                            handler_inserted = True
                            logger.info(f"Обработчик добавлен перед строкой {i+1}")
                            break
            else:
                logger.info("Обработчик уже существует")
            
            # Обновляем тип возврата _route_by_stage
            for i, line in enumerate(lines):
                if 'Literal[' in line and 'greeting' in line and f'"{stage_key}"' not in ''.join(lines[i:i+2]):
                    # Ищем строку с Literal и добавляем стадию
                    if '"reschedule"' in line:
                        lines[i] = line.replace('"reschedule",', f'"reschedule", "{stage_key}",')
                        logger.info(f"Тип Literal обновлён на строке {i+1}")
                    break
            
            # Обновляем проверку стадий в _route_by_stage
            for i, line in enumerate(lines):
                if 'if stage not in [' in line and f'"{stage_key}"' not in ''.join(lines[i:i+2]):
                    if '"reschedule"' in line:
                        lines[i] = line.replace('"reschedule",', f'"reschedule", "{stage_key}",')
                        logger.info(f"Проверка стадий обновлена на строке {i+1}")
                    break
            
            with open(self.graph_file, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            logger.info("✅ Граф успешно обновлён")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении в граф: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            return False
    
    def _add_to_dialogue_stages(self, stage_key: str, stage_name: str) -> bool:
        """Добавить стадию в dialogue_stages.py"""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"=== ДОБАВЛЕНИЕ В DIALOGUE_STAGES ===")
        logger.info(f"stage_key: {stage_key}, stage_name: {stage_name}")
        logger.info(f"Файл существует: {self.dialogue_stages_file.exists()}")
        
        if not self.dialogue_stages_file.exists():
            logger.error(f"Файл не существует: {self.dialogue_stages_file}")
            return False
        
        try:
            with open(self.dialogue_stages_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            enum_name = stage_key.upper().replace('-', '_')
            
            # Проверяем, есть ли уже эта стадия
            for line in lines:
                if enum_name in line and f'"{stage_key}"' in line:
                    return True
            
            # Ищем строку с UNKNOWN и добавляем перед ней
            new_line = f'    {enum_name} = "{stage_key}"          # {stage_name}\n'
            
            for i, line in enumerate(lines):
                if 'UNKNOWN = "unknown"' in line:
                    lines.insert(i, new_line)
                    break
            else:
                # Если не нашли UNKNOWN, добавляем в конец перед закрывающей скобкой
                for i in range(len(lines) - 1, -1, -1):
                    if lines[i].strip() == ')':
                        lines.insert(i, new_line)
                        break
            
            with open(self.dialogue_stages_file, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            logger.info("✅ dialogue_stages.py успешно обновлён")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении в dialogue_stages: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            return False
    
    def _remove_from_dialogue_stages(self, stage_key: str) -> bool:
        """Удалить стадию из dialogue_stages.py"""
        if not self.dialogue_stages_file.exists():
            return False
        
        try:
            with open(self.dialogue_stages_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Удаляем строку со стадией
            enum_name = stage_key.upper().replace('-', '_')
            pattern = rf'\s*{re.escape(enum_name)} = "{re.escape(stage_key)}".*?\n'
            new_content = re.sub(pattern, '', content)
            
            with open(self.dialogue_stages_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return True
        except Exception as e:
            print(f"Ошибка при удалении из dialogue_stages: {e}")
            return False
    
    def _get_tool_module_mapping(self) -> Dict[str, str]:
        """Определяет модуль для каждого инструмента через парсинг файлов"""
        module_mapping = {}
        tools_dir = self.project_root / "src" / "agents" / "tools"
        
        if not tools_dir.exists():
            return {}
        
        # Проходим по всем файлам в директории tools
        for file_path in tools_dir.iterdir():
            if not file_path.is_file() or file_path.name.startswith('__') or file_path.suffix != '.py':
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Ищем классы инструментов в этом файле
                class_pattern = r'class\s+(\w+)\s*\([^)]*BaseModel[^)]*\):'
                class_matches = list(re.finditer(class_pattern, content))
                
                # Имя модуля - это имя файла без расширения
                module_name = file_path.stem
                
                for match in class_matches:
                    class_name = match.group(1)
                    class_start = match.end()
                    
                    # Ищем конец класса (следующий class или конец файла)
                    next_class_match = re.search(r'\nclass\s+\w+', content[class_start:])
                    if next_class_match:
                        class_end = class_start + next_class_match.start()
                    else:
                        class_end = len(content)
                    
                    # Извлекаем содержимое класса
                    class_content = content[class_start:class_end]
                    
                    # Проверяем, что у класса есть метод process
                    if 'def process' in class_content:
                        module_mapping[class_name] = module_name
                        
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Не удалось прочитать файл {file_path.name}: {e}")
        
        return module_mapping
    
    def update_stage_tools(self, file_path: str, tools: List[str]) -> bool:
        """Обновить инструменты в файле агента"""
        import re
        try:
            full_path = self.project_root / file_path
            if not full_path.exists():
                return False
            
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines(keepends=True)
            
            # Определяем модуль для каждого инструмента
            tool_module_mapping = self._get_tool_module_mapping()
            
            # Группируем инструменты по модулям
            tools_by_module = {}
            for tool in tools:
                module = tool_module_mapping.get(tool, 'service_tools')
                if module not in tools_by_module:
                    tools_by_module[module] = []
                tools_by_module[module].append(tool)
            
            # Удаляем все старые импорты инструментов
            new_lines = []
            skip_imports = False
            for i, line in enumerate(lines):
                # Пропускаем строки с импортами инструментов
                if 'from .tools.' in line and ('import' in line):
                    # Проверяем, является ли это импортом инструмента
                    if any(tool in line for tool in self.get_available_tools()):
                        skip_imports = True
                        continue
                
                # Если это пустая строка после удаленных импортов, пропускаем лишние
                if skip_imports and line.strip() == '':
                    # Проверяем, есть ли еще импорты инструментов ниже
                    has_more_imports = False
                    for j in range(i + 1, min(i + 3, len(lines))):
                        if 'from .tools.' in lines[j] and any(tool in lines[j] for tool in self.get_available_tools()):
                            has_more_imports = True
                            break
                    if not has_more_imports:
                        skip_imports = False
                        continue
                
                new_lines.append(line)
            
            lines = new_lines
            
            # Находим место для вставки новых импортов (после docstring, перед другими импортами)
            insert_pos = None
            for i, line in enumerate(lines):
                if '"""' in line:
                    # Ищем конец docstring
                    for j in range(i + 1, len(lines)):
                        if '"""' in lines[j]:
                            insert_pos = j + 1
                            break
                    break
            
            if insert_pos is None:
                # Если docstring не найден, ищем после первого импорта
                for i, line in enumerate(lines):
                    if line.strip().startswith('from ') or line.strip().startswith('import '):
                        insert_pos = i
                        break
            
            if insert_pos is None:
                insert_pos = 0
            
            # Добавляем новые импорты
            import_lines = []
            for module, module_tools in sorted(tools_by_module.items()):
                if module_tools:
                    tools_list = ', '.join(sorted(module_tools))
                    import_line = f'from .tools.{module} import {tools_list}\n'
                    import_lines.append(import_line)
            
            # Вставляем импорты
            if import_lines:
                # Добавляем пустую строку перед импортами, если нужно
                if insert_pos > 0 and lines[insert_pos - 1].strip() != '':
                    lines.insert(insert_pos, '\n')
                    insert_pos += 1
                
                for import_line in import_lines:
                    lines.insert(insert_pos, import_line)
                    insert_pos += 1
            
            # Удаляем все вхождения tools= в super().__init__()
            # Ищем именно .__init__( и обрабатываем ТОЛЬКО его параметры
            # Игнорируем все что до .__init__(, включая super()
            super_init_start = None
            super_init_end = None
            
            for i, line in enumerate(lines):
                if '.__init__(' in line:
                    super_init_start = i
                    # Ищем открывающую скобку __init__
                    paren_count = 0
                    found_open = False
                    init_open_pos = line.find('.__init__(')
                    
                    # Считаем скобки от .__init__(
                    for j in range(i, min(i + 15, len(lines))):
                        start_char = 0
                        if j == i:
                            start_char = init_open_pos + len('.__init__(')
                        
                        for char_idx in range(start_char, len(lines[j])):
                            char = lines[j][char_idx]
                            if char == '(':
                                paren_count += 1
                                found_open = True
                            elif char == ')':
                                paren_count -= 1
                                if paren_count == 0 and found_open:
                                    super_init_end = j
                                    break
                        if super_init_end is not None:
                            break
                    break
            
            if super_init_start is not None and super_init_end is not None:
                # Собираем только строки с параметрами __init__
                super_init_lines = []
                init_open_pos = lines[super_init_start].find('.__init__(')
                
                # Берем часть строки после .__init__(
                first_line_content = lines[super_init_start][init_open_pos + len('.__init__('):]
                super_init_lines.append(first_line_content)
                
                # Добавляем остальные строки до закрывающей скобки
                for i in range(super_init_start + 1, super_init_end + 1):
                    super_init_lines.append(lines[i])
                
                # Объединяем в одну строку для обработки
                init_params_content = ''.join(super_init_lines)
                
                # Удаляем tools= только из параметров __init__
                init_params_content = re.sub(r',\s*tools\s*=\s*\[[^\]]*\]', '', init_params_content)
                init_params_content = re.sub(r',\s*tools\s*=\s*None', '', init_params_content)
                init_params_content = re.sub(r'^\s*tools\s*=\s*\[[^\]]*\]\s*,?\s*', '', init_params_content)
                init_params_content = re.sub(r'^\s*tools\s*=\s*None\s*,?\s*', '', init_params_content)
                
                # Убираем лишние запятые
                init_params_content = re.sub(r',\s*,+', ',', init_params_content)
                init_params_content = re.sub(r',\s*\)', ')', init_params_content)
                init_params_content = re.sub(r'^\s*,+', '', init_params_content)
                
                # Разбиваем обратно на строки
                new_init_params_lines = init_params_content.splitlines(keepends=True)
                
                # Заменяем только часть после .__init__(
                # Первая строка: часть до .__init__( + новые параметры
                before_init = lines[super_init_start][:init_open_pos + len('.__init__(')]
                if new_init_params_lines:
                    lines[super_init_start] = before_init + new_init_params_lines[0]
                    # Заменяем остальные строки
                    if len(new_init_params_lines) > 1:
                        lines[super_init_start + 1:super_init_end + 1] = new_init_params_lines[1:]
                    else:
                        # Если параметры уместились в одну строку, удаляем остальные
                        for idx in range(super_init_end, super_init_start, -1):
                            del lines[idx]
                else:
                    lines[super_init_start] = before_init + new_init_params_lines[0] if new_init_params_lines else before_init + ')'
                
                # Теперь добавляем tools= в правильное место - ТОЛЬКО в параметры __init__
                # Ищем закрывающую скобку __init__ в обновленных строках
                for i in range(super_init_start, min(super_init_start + 15, len(lines))):
                    if '.__init__(' in lines[i]:
                        # Нашли .__init__(, ищем закрывающую скобку
                        init_pos = lines[i].find('.__init__(')
                        paren_count = 0
                        found_init_open = False
                        
                        for j in range(i, min(i + 15, len(lines))):
                            start_char = 0
                            if j == i:
                                start_char = init_pos + len('.__init__(')
                            
                            for char_idx in range(start_char, len(lines[j])):
                                char = lines[j][char_idx]
                                if char == '(':
                                    paren_count += 1
                                    found_init_open = True
                                elif char == ')':
                                    paren_count -= 1
                                    if paren_count == 0 and found_init_open:
                                        # Нашли закрывающую скобку __init__
                                        if tools:
                                            quoted_tools = ['"' + tool + '"' for tool in sorted(tools)]
                                            tools_list = ', '.join(quoted_tools)
                                            
                                            before_bracket = lines[j][:char_idx].rstrip()
                                            if before_bracket and not before_bracket.endswith('('):
                                                if not before_bracket.endswith(','):
                                                    tools_param = f', tools=[{tools_list}]'
                                                else:
                                                    tools_param = f' tools=[{tools_list}]'
                                            else:
                                                tools_param = f'tools=[{tools_list}]'
                                            
                                            lines[j] = lines[j][:char_idx] + tools_param + lines[j][char_idx:]
                                        break
                            if paren_count == 0:
                                break
                        break
            
            # Сохраняем файл
            with open(full_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            # Проверяем синтаксис
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content_check = f.read()
                ast.parse(content_check)
            except SyntaxError as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Синтаксическая ошибка после обновления инструментов: {e}")
                return False
            
            return True
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при обновлении инструментов: {e}", exc_info=True)
            return False
    
    def load_tool_classes(self) -> Dict[str, type]:
        """
        Получить список классов инструментов через парсинг файлов (без импорта)
        Возвращает словарь с именами инструментов, но без самих классов
        """
        tool_names = {}
        tools_dir = self.project_root / "src" / "agents" / "tools"
        
        if not tools_dir.exists():
            return {}
        
        # Проходим по всем файлам в директории tools
        for file_path in tools_dir.iterdir():
            # Пропускаем __init__.py и другие служебные файлы
            if not file_path.is_file() or file_path.name.startswith('__') or file_path.suffix != '.py':
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Ищем классы, которые наследуются от BaseModel
                # Паттерн: class ИмяКласса(BaseModel): ... def process(
                class_pattern = r'class\s+(\w+)\s*\([^)]*BaseModel[^)]*\):'
                class_matches = list(re.finditer(class_pattern, content))
                
                for match in class_matches:
                    class_name = match.group(1)
                    class_start = match.end()
                    
                    # Ищем конец класса (следующий class или конец файла)
                    next_class_match = re.search(r'\nclass\s+\w+', content[class_start:])
                    if next_class_match:
                        class_end = class_start + next_class_match.start()
                    else:
                        class_end = len(content)
                    
                    # Извлекаем содержимое класса
                    class_content = content[class_start:class_end]
                    
                    # Проверяем, что у класса есть метод process
                    if 'def process' in class_content:
                        tool_names[class_name] = None  # Храним только имя, без класса
                        
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Не удалось прочитать файл {file_path.name}: {e}")
        
        return tool_names
    
    def get_available_tools(self) -> List[str]:
        """Получить список доступных инструментов (через парсинг файлов)"""
        tool_classes = self.load_tool_classes()
        return sorted(tool_classes.keys())
    
    def get_stage_detector_instruction(self) -> str:
        """Получить промпт StageDetectorAgent из файла"""
        try:
            if not self.stage_detector_file.exists():
                return ""
            
            with open(self.stage_detector_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Извлекаем промпт из файла
            instruction_match = re.search(r'instruction\s*=\s*"""(.*?)"""', content, re.DOTALL)
            if instruction_match:
                return instruction_match.group(1).strip()
            
            return ""
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при загрузке промпта определителя: {e}", exc_info=True)
            return ""
    
    def save_stage_detector_instruction(self, new_instruction: str) -> bool:
        """Сохранить промпт StageDetectorAgent в файл"""
        try:
            if not self.stage_detector_file.exists():
                return False
            
            # Используем тот же метод, что и для обычных стадий
            file_path = str(self.stage_detector_file.relative_to(self.project_root))
            return self.save_stage_instruction(file_path, new_instruction)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при сохранении промпта определителя: {e}", exc_info=True)
            return False
    
    def add_stage_to_detector(self, stage_key: str, stage_name: str, stage_description: str) -> bool:
        """Добавить описание стадии в промпт определителя"""
        try:
            # Получаем текущий промпт
            current_instruction = self.get_stage_detector_instruction()
            
            # Проверяем, есть ли уже эта стадия в промпте
            if f'- {stage_key}:' in current_instruction:
                # Обновляем существующее описание
                pattern = rf'(- {re.escape(stage_key)}:).*?(\n)'
                replacement = rf'\1 {stage_description}\2'
                new_instruction = re.sub(pattern, replacement, current_instruction, flags=re.DOTALL)
            else:
                # Добавляем новую стадию перед последней строкой
                lines = current_instruction.split('\n')
                new_line = f'- {stage_key}: {stage_description}'
                
                # Ищем место перед последней строкой (обычно это "Верни ТОЛЬКО...")
                for i in range(len(lines) - 1, -1, -1):
                    if lines[i].strip() and not lines[i].strip().startswith('- '):
                        lines.insert(i, new_line)
                        break
                else:
                    lines.append(new_line)
                
                new_instruction = '\n'.join(lines)
            
            # Сохраняем обновлённый промпт
            return self.save_stage_detector_instruction(new_instruction)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при добавлении описания стадии: {e}", exc_info=True)
            return False
    
    def remove_stage_from_detector(self, stage_key: str, stage_name: str) -> bool:
        """Удалить описание стадии из промпта определителя"""
        try:
            # Получаем текущий промпт
            current_instruction = self.get_stage_detector_instruction()
            
            # Удаляем строку со стадией
            pattern = rf'- {re.escape(stage_key)}:.*?\n'
            new_instruction = re.sub(pattern, '', current_instruction)
            
            # Сохраняем обновлённый промпт
            return self.save_stage_detector_instruction(new_instruction)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при удалении описания стадии: {e}", exc_info=True)
            return False
    
    def remove_stage_from_detector_old(self, stage_key: str, stage_name: str) -> bool:
        """Удалить описание стадии из промпта StageDetectorAgent"""
        if not self.stage_detector_file.exists():
            return False
        
        try:
            with open(self.stage_detector_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Удаляем секцию стадии - ищем по ключу (он идёт первым после номера)
            # Паттерн: ### N. stage_key ... до следующего ### или ##
            pattern1 = rf'### \d+\. {re.escape(stage_key)}.*?(?=\n\n###|\n\n## Правила)'
            new_content = re.sub(pattern1, '', content, flags=re.DOTALL)
            
            # Если не нашлось по ключу, пробуем по имени в скобках
            if new_content == content:
                pattern2 = rf'### \d+\. [^\n]*\([^)]*{re.escape(stage_name)}[^)]*\).*?(?=\n\n###|\n\n## Правила)'
                new_content = re.sub(pattern2, '', content, flags=re.DOTALL)
            
            # Перенумеровываем оставшиеся стадии
            stage_matches = list(re.finditer(r'### (\d+)\.', new_content))
            for i, match in enumerate(stage_matches, 1):
                old_number = match.group(1)
                if int(old_number) != i:
                    # Заменяем номер
                    start, end = match.span()
                    new_content = new_content[:start] + f'### {i}.' + new_content[end:]
            
            with open(self.stage_detector_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            return True
        except Exception as e:
            print(f"Ошибка при удалении стадии из детектора: {e}")
            import traceback
            traceback.print_exc()
            return False

