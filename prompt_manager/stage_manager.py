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
        self.graph_file = self.project_root / "src" / "graph" / "booking_graph.py"
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
        try:
            full_path = self.project_root / file_path
            if not full_path.exists():
                return False
            
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Ищем строку с instruction = """
            instruction_start_idx = None
            instruction_end_idx = None
            
            for i, line in enumerate(lines):
                # Ищем строку вида: instruction = """ или instruction=""" 
                if re.search(r'instruction\s*=\s*"""', line):
                    instruction_start_idx = i
                    # Проверяем, не закрыта ли кавычка на той же строке
                    if line.count('"""') >= 2:
                        # Закрыта на той же строке (однострочный промпт)
                        instruction_end_idx = i
                    else:
                        # Ищем закрывающую тройную кавычку на отдельной строке
                        for j in range(i + 1, len(lines)):
                            if '"""' in lines[j]:
                                instruction_end_idx = j
                                break
                    break
            
            if instruction_start_idx is None or instruction_end_idx is None:
                # Fallback на старый метод, если не нашли точные границы
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Экранируем специальные символы в new_instruction для regex
                escaped_instruction = re.escape(new_instruction)
                # Но нам нужны не экранированные, а просто замена содержимого
                pattern = r'(instruction\s*=\s*""").*?(""")'
                replacement = r'\1' + new_instruction + r'\2'
                new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
                
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
            else:
                # Безопасная замена: сохраняем всё до instruction, вставляем новый промпт, сохраняем всё после
                new_lines = []
                
                if instruction_start_idx == instruction_end_idx:
                    # Однострочный промпт - закрывающая кавычка на той же строке
                    start_line = lines[instruction_start_idx]
                    # Разделяем строку на части: до """ и после """
                    parts = start_line.split('"""', 2)
                    if len(parts) >= 3:
                        # parts[0] - до первой """, parts[1] - старый промпт, parts[2] - после второй """
                        new_line = parts[0] + '"""' + new_instruction + '"""' + parts[2]
                        new_lines.extend(lines[:instruction_start_idx])
                        new_lines.append(new_line)
                        new_lines.extend(lines[instruction_start_idx + 1:])
                    else:
                        # Не удалось разделить - используем fallback
                        raise ValueError("Не удалось обработать однострочный промпт")
                else:
                    # Многострочный промпт
                    # Добавляем строки до instruction (включая строку с instruction = """)
                    new_lines.extend(lines[:instruction_start_idx + 1])
                    
                    # Добавляем новый промпт (каждая строка отдельно для сохранения форматирования)
                    # Если промпт многострочный, разбиваем на строки
                    if '\n' in new_instruction:
                        prompt_lines = new_instruction.split('\n')
                        for prompt_line in prompt_lines:
                            new_lines.append(prompt_line + '\n')
                    else:
                        new_lines.append(new_instruction + '\n')
                    
                    # Добавляем закрывающую тройную кавычку
                    new_lines.append(lines[instruction_end_idx])
                    
                    # Добавляем оставшиеся строки
                    new_lines.extend(lines[instruction_end_idx + 1:])
                
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
            
            # Проверяем синтаксис Python после сохранения
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                ast.parse(content)
            except SyntaxError as e:
                # Если синтаксическая ошибка, пробуем восстановить через более простой метод
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Синтаксическая ошибка после сохранения: {e}")
                # Пробуем восстановить через regex с экранированием
                pattern = r'(instruction\s*=\s*""").*?(""")'
                # Экранируем тройные кавычки в промпте, если они есть
                safe_instruction = new_instruction.replace('"""', '\\"\\"\\"')
                replacement = r'\1' + safe_instruction + r'\2'
                new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
                # Но это не сработает, если в промпте действительно нужны тройные кавычки
                # Поэтому просто возвращаем False
                return False
            
            return True
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при сохранении: {e}", exc_info=True)
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
        tools_imports = []
        tools_list = []
        
        # Используем динамический список инструментов
        available_tools = self.get_available_tools()
        for tool_name in tools:
            if tool_name in available_tools:
                tools_imports.append(tool_name)
                tools_list.append(tool_name)
        
        imports = ""
        tools_param = "None"
        if tools_imports:
            imports = f"from .tools.service_tools import {', '.join(tools_imports)}\n"
            tools_param = f"[{', '.join(tools_list)}]"
        
        file_content = f'''"""
Агент для стадии {stage_name}
"""
{imports}from .base_agent import BaseAgent
from ..services.langgraph_service import LangGraphService


class {class_name}(BaseAgent):
    """Агент для стадии {stage_name}"""
    
    def __init__(self, langgraph_service: LangGraphService):
        instruction = """{instruction}"""
        
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
        """Удалить стадию из booking_graph.py"""
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
            handler_pattern = rf'def _handle_{re.escape(stage_key)}\(self, state: BookingState\) -> BookingState:.*?return.*?\n\n'
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
        """Добавить стадию в booking_graph.py"""
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
            handler_code = f'''    def _handle_{stage_key}(self, state: BookingState) -> BookingState:
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
        """Определяет модуль для каждого инструмента"""
        tool_classes = self.load_tool_classes()
        module_mapping = {}
        
        for tool_name, tool_class in tool_classes.items():
            # Получаем модуль класса
            module_name = tool_class.__module__
            # Извлекаем имя модуля (последняя часть после точки)
            if '.' in module_name:
                module_parts = module_name.split('.')
                # Ищем часть, которая начинается с 'tools'
                tools_idx = None
                for i, part in enumerate(module_parts):
                    if part == 'tools':
                        tools_idx = i
                        break
                
                if tools_idx is not None and tools_idx + 1 < len(module_parts):
                    # Берем имя модуля после 'tools'
                    module_file = module_parts[tools_idx + 1]
                    module_mapping[tool_name] = module_file
                else:
                    # По умолчанию service_tools
                    module_mapping[tool_name] = 'service_tools'
            else:
                module_mapping[tool_name] = 'service_tools'
        
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
            # Ищем super().__init__ и удаляем все параметры tools
            super_init_start = None
            super_init_end = None
            
            for i, line in enumerate(lines):
                if 'super().__init__(' in line:
                    super_init_start = i
                    # Ищем закрывающую скобку
                    paren_count = 0
                    found_open = False
                    for j in range(i, min(i + 15, len(lines))):
                        for char in lines[j]:
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
            
            # Удаляем все вхождения tools= в super().__init__()
            # Ищем super().__init__ и удаляем все параметры tools
            super_init_start = None
            super_init_end = None
            
            for i, line in enumerate(lines):
                if 'super().__init__(' in line:
                    super_init_start = i
                    # Ищем закрывающую скобку
                    paren_count = 0
                    found_open = False
                    for j in range(i, min(i + 15, len(lines))):
                        for char in lines[j]:
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
                # Собираем все строки между super_init_start и super_init_end
                super_init_lines = []
                for i in range(super_init_start, super_init_end + 1):
                    super_init_lines.append(lines[i])
                
                # Объединяем в одну строку для обработки
                super_init_content = ''.join(super_init_lines)
                
                # Удаляем все вхождения tools=... (включая запятые перед/после)
                # Паттерн для удаления: запятая (опционально), пробелы, tools=, значение до запятой или закрывающей скобки
                super_init_content = re.sub(r',?\s*tools\s*=\s*\[[^\]]*\],?\s*', '', super_init_content)
                super_init_content = re.sub(r',?\s*tools\s*=\s*None,?\s*', '', super_init_content)
                
                # Разбиваем обратно на строки
                new_super_lines = super_init_content.splitlines(keepends=True)
                
                # Заменяем строки
                lines[super_init_start:super_init_end + 1] = new_super_lines
                
                # Теперь добавляем tools= в правильное место
                # Ищем закрывающую скобку в новых строках
                for i in range(super_init_start, len(lines)):
                    if ')' in lines[i]:
                        # Вставляем tools перед закрывающей скобкой
                        if tools:
                            tools_list = ', '.join(sorted(tools))
                            bracket_pos = lines[i].rfind(')')
                            if bracket_pos > 0:
                                before_bracket = lines[i][:bracket_pos].rstrip()
                                if before_bracket and not before_bracket.endswith(','):
                                    tools_param = f', tools=[{tools_list}]'
                                else:
                                    tools_param = f'tools=[{tools_list}]'
                                lines[i] = lines[i][:bracket_pos] + tools_param + lines[i][bracket_pos:]
                            else:
                                # Если скобка в начале строки, добавляем на предыдущей строке
                                if i > super_init_start:
                                    prev_line = lines[i - 1].rstrip()
                                    if prev_line and not prev_line.endswith(','):
                                        tools_param = f', tools=[{tools_list}]'
                                    else:
                                        tools_param = f'tools=[{tools_list}]'
                                    lines[i - 1] = prev_line + tools_param + '\n'
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
        """Динамически загрузить все классы инструментов из всех модулей в пакете tools"""
        try:
            import importlib
            import pkgutil
            from src.agents import tools as tools_package
            
            tool_classes = {}
            
            # Проходим по всем модулям в пакете tools
            for importer, modname, ispkg in pkgutil.iter_modules(tools_package.__path__, tools_package.__name__ + "."):
                if not ispkg:  # Пропускаем подпакеты, только модули
                    try:
                        module = importlib.import_module(modname)
                        # Проходим по всем атрибутам модуля
                        for name, obj in inspect.getmembers(module):
                            # Проверяем, что это класс, наследуется от BaseModel и имеет метод process
                            if (inspect.isclass(obj) and 
                                issubclass(obj, BaseModel) and 
                                obj != BaseModel and
                                hasattr(obj, 'process') and
                                callable(getattr(obj, 'process'))):
                                tool_classes[name] = obj
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Не удалось загрузить модуль {modname}: {e}")
            
            return tool_classes
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при загрузке инструментов: {e}", exc_info=True)
            # Возвращаем пустой словарь в случае ошибки
            return {}
    
    def get_available_tools(self) -> List[str]:
        """Получить список доступных инструментов (динамически)"""
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

