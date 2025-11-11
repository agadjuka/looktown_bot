"""
Модуль для загрузки и анализа инструментов
"""
import inspect
from typing import List, Dict, Any, Optional, Type
from pydantic import BaseModel, Field
from pathlib import Path
import sys
import os
import importlib.util

# Загружаем переменные окружения из .env файла проекта
from dotenv import load_dotenv

# Определяем корень проекта и загружаем .env
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent
load_dotenv(project_root / '.env')

# Добавляем корень проекта в sys.path
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class ToolInfo:
    """Информация об инструменте"""
    
    def __init__(self, tool_class: Type[BaseModel]):
        self.tool_class = tool_class
        self.name = tool_class.__name__
        self.description = self._extract_description()
        self.parameters = self._extract_parameters()
        self.module_path = inspect.getfile(tool_class)
    
    def _extract_description(self) -> str:
        """Извлекает описание инструмента из docstring"""
        doc = inspect.getdoc(self.tool_class)
        if doc:
            # Берем первую строку или весь docstring если он короткий
            lines = doc.strip().split('\n')
            return lines[0] if lines else ""
        return ""
    
    def _extract_parameters(self) -> List[Dict[str, Any]]:
        """Извлекает параметры инструмента из полей модели"""
        parameters = []
        
        # Получаем схему модели
        try:
            schema = self.tool_class.model_json_schema()
            properties = schema.get('properties', {})
            required = schema.get('required', [])
            
            for param_name, param_info in properties.items():
                # Определяем тип параметра
                param_type = param_info.get('type', 'string')
                # Обрабатываем union типы (например, Optional[str])
                if isinstance(param_type, list):
                    # Берем первый не-None тип
                    param_type = next((t for t in param_type if t != 'null'), 'string')
                
                param_data = {
                    'name': param_name,
                    'type': param_type,
                    'description': param_info.get('description', ''),
                    'required': param_name in required,
                    'default': param_info.get('default', None)
                }
                parameters.append(param_data)
        except Exception as e:
            print(f"Ошибка при извлечении параметров для {self.name}: {e}")
        
        return parameters
    
    def get_full_description(self) -> str:
        """Возвращает полное описание инструмента"""
        doc = inspect.getdoc(self.tool_class)
        return doc if doc else self.description


class ToolLoader:
    """Загрузчик инструментов из модулей"""
    
    def __init__(self, tools_dir: Optional[Path] = None):
        # Определяем путь к папке tools относительно этого файла
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent
        
        if tools_dir is None:
            tools_dir = project_root / "src" / "agents" / "tools"
        
        self.tools_dir = tools_dir
        self.tools: Dict[str, ToolInfo] = {}
        self.errors: List[str] = []
    
    def _create_fake_packages(self):
        """Создает фиктивные пакеты в sys.modules для избежания циклических импортов"""
        import types
        
        packages = ['src', 'src.agents', 'src.agents.tools']
        for pkg_name in packages:
            if pkg_name not in sys.modules:
                pkg = types.ModuleType(pkg_name)
                pkg.__name__ = pkg_name
                pkg.__path__ = []
                sys.modules[pkg_name] = pkg
    
    def _load_dependency_directly(self, file_path: Path, module_name: str):
        """Загружает зависимый модуль напрямую из файла"""
        if module_name in sys.modules:
            return sys.modules[module_name]
        
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Не удалось создать spec для {file_path}")
        
        module = importlib.util.module_from_spec(spec)
        module.__package__ = 'src.agents.tools'
        module.__name__ = module_name
        
        # Добавляем в sys.modules перед выполнением
        sys.modules[module_name] = module
        
        # Выполняем модуль
        spec.loader.exec_module(module)
        return module
    
    def load_all_tools(self) -> Dict[str, ToolInfo]:
        """Загружает все инструменты из всех модулей в папке tools"""
        self.tools = {}
        errors = []
        
        # Создаем фиктивные пакеты ПЕРЕД загрузкой модулей
        self._create_fake_packages()
        
        # Загружаем зависимости ПЕРЕД основными модулями
        dependencies = [
            ('services_data_loader.py', 'src.agents.tools.services_data_loader'),
            ('yclients_service.py', 'src.agents.tools.yclients_service'),
            ('book_times_logic.py', 'src.agents.tools.book_times_logic'),
            ('phone_utils.py', 'src.agents.tools.phone_utils'),
            ('create_booking_logic.py', 'src.agents.tools.create_booking_logic'),
            ('service_master_mapper.py', 'src.agents.tools.service_master_mapper'),
            ('find_master_by_service_logic.py', 'src.agents.tools.find_master_by_service_logic'),
            ('client_records_logic.py', 'src.agents.tools.client_records_logic'),
        ]
        
        for dep_file, dep_module_name in dependencies:
            dep_path = self.tools_dir / dep_file
            if dep_path.exists():
                try:
                    self._load_dependency_directly(dep_path, dep_module_name)
                except Exception as e:
                    print(f"⚠️ Предупреждение: не удалось загрузить {dep_file}: {e}")
        
        # Список модулей с инструментами (файлы, которые содержат классы инструментов)
        tool_modules = [
            'service_tools.py',
            'client_records_tools.py',
        ]
        
        loaded_count = 0
        
        for module_file in tool_modules:
            module_path = self.tools_dir / module_file
            
            if not module_path.exists():
                print(f"⚠️ Файл {module_file} не найден, пропускаем")
                continue
            
            try:
                # Формируем имя модуля
                module_name = f"src.agents.tools.{module_path.stem}"
                
                # Загружаем модуль
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                
                if spec is None or spec.loader is None:
                    error_msg = f"Не удалось создать spec для {module_path}"
                    errors.append(error_msg)
                    print(f"❌ {error_msg}")
                    continue
                
                # Создаем модуль
                module = importlib.util.module_from_spec(spec)
                module.__package__ = 'src.agents.tools'
                module.__name__ = module_name
                
                # Добавляем в sys.modules перед выполнением
                sys.modules[module_name] = module
                
                # Выполняем модуль
                spec.loader.exec_module(module)
                
                # Ищем все классы инструментов в модуле
                for name, obj in inspect.getmembers(module):
                    # Проверяем, что это класс, наследуется от BaseModel и имеет метод process
                    if (inspect.isclass(obj) and 
                        issubclass(obj, BaseModel) and 
                        obj != BaseModel and
                        hasattr(obj, 'process') and
                        callable(getattr(obj, 'process'))):
                        
                        try:
                            # Проверяем, что это действительно инструмент
                            if not inspect.isclass(obj):
                                errors.append(f"{name}: не является классом")
                                continue
                            
                            if not issubclass(obj, BaseModel):
                                errors.append(f"{name}: не является подклассом BaseModel")
                                continue
                            
                            if not hasattr(obj, 'process'):
                                errors.append(f"{name}: класс не имеет метод process")
                                continue
                            
                            # Создаем ToolInfo
                            tool_info = ToolInfo(obj)
                            self.tools[tool_info.name] = tool_info
                            loaded_count += 1
                            print(f"✅ Загружен инструмент: {name}")
                            
                        except Exception as e:
                            error_msg = f"{name}: {str(e)}"
                            errors.append(error_msg)
                            print(f"❌ Ошибка при загрузке {name}: {e}")
                            import traceback
                            traceback.print_exc()
                
            except ImportError as e:
                error_msg = f"Ошибка импорта модуля {module_file}: {e}"
                errors.append(error_msg)
                print(f"❌ {error_msg}")
                import traceback
                traceback.print_exc()
            except Exception as e:
                error_msg = f"Критическая ошибка при загрузке модуля {module_file}: {e}"
                errors.append(error_msg)
                print(f"❌ {error_msg}")
                import traceback
                traceback.print_exc()
        
        if loaded_count > 0:
            print(f"✅ Загружено {loaded_count} инструментов из {len(tool_modules)} модулей")
        
        if errors:
            self.errors = errors
        
        print(f"Всего загружено инструментов: {len(self.tools)}")
        if errors:
            print(f"Всего ошибок: {len(errors)}")
        
        return self.tools
    
    def get_tool(self, tool_name: str) -> Optional[ToolInfo]:
        """Получает информацию об инструменте по имени"""
        return self.tools.get(tool_name)
    
    def get_all_tool_names(self) -> List[str]:
        """Возвращает список всех имен инструментов"""
        return sorted(self.tools.keys())


def create_mock_thread():
    """Создает mock объект Thread для тестирования"""
    from unittest.mock import MagicMock
    thread = MagicMock()
    thread.id = "test_thread_id"
    return thread

