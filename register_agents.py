"""
Скрипт для регистрации всех агентов в Yandex Cloud и YDB
Создает Assistant для каждого агента и сохраняет запись в базе данных
"""
import os
import sys
import re
import logging
from pathlib import Path
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Добавляем корень проекта в путь
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Загружаем переменные окружения
load_dotenv()

from src.services.langgraph_service import LangGraphService
from src.ydb_client import get_ydb_client


def parse_agent_file(file_path: Path) -> dict:
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
            instruction_match = re.search(r'instruction\s*=\s*"""(.*?)"""', content, re.DOTALL | re.MULTILINE)
        
        instruction = instruction_match.group(1).strip() if instruction_match else ""
        
        # Извлекаем agent_name
        agent_name_match = re.search(r'agent_name\s*=\s*["\']([^"\']+)["\']', content)
        agent_name = agent_name_match.group(1) if agent_name_match else class_name
        
        # Определяем используемые инструменты из импортов
        tools = []
        # Ищем импорты инструментов из service_tools
        tools_import_match = re.search(r'from\s+\.tools\.service_tools\s+import\s+([^\n]+)', content)
        if tools_import_match:
            tools_str = tools_import_match.group(1)
            # Извлекаем имена классов инструментов (убираем возможные переносы строк)
            tools_str = tools_str.replace('\n', ' ').strip()
            # Разбиваем по запятым и очищаем
            tools_list = [t.strip() for t in tools_str.split(',')]
            # Фильтруем только валидные имена классов
            valid_tools = ['GetCategories', 'GetServices', 'BookTimes', 'CreateBooking']
            tools = [t for t in tools_list if t in valid_tools]
        
        # Определяем стадию из имени файла
        stage = file_path.stem
        if stage.endswith('_agent'):
            stage = stage[:-6]
        
        return {
            'file_path': str(file_path.relative_to(project_root)),
            'class_name': class_name,
            'name': agent_name,
            'stage': stage,
            'instruction': instruction,
            'tools': tools,
            'full_path': str(file_path)
        }
    except Exception as e:
        logger.error(f"Ошибка при парсинге {file_path}: {e}")
        return None


def register_all_agents(force: bool = False):
    """Регистрация всех агентов в Yandex Cloud и YDB"""
    logger.info("=== НАЧАЛО РЕГИСТРАЦИИ АГЕНТОВ ===")
    if force:
        logger.info("⚠️ Режим FORCE: существующие агенты будут пересозданы")
    else:
        logger.info("ℹ️ Режим по умолчанию: существующие агенты будут пересозданы (старые удаляются)")
    
    try:
        # Инициализируем сервисы
        logger.info("Инициализация сервисов...")
        langgraph_service = LangGraphService()
        ydb_client = get_ydb_client()
        
        logger.info("✅ Сервисы инициализированы")
        
        # Получаем все стадии (агенты)
        logger.info("Получение списка агентов...")
        agents_dir = project_root / "src" / "agents"
        excluded = {'__init__.py', 'base_agent.py', 'dialogue_stages.py', 'stage_detector_agent.py', 'tools', '__pycache__'}
        
        agents = []
        if agents_dir.exists():
            for file_path in agents_dir.iterdir():
                if file_path.is_file() and file_path.suffix == '.py' and file_path.name not in excluded:
                    agent_info = parse_agent_file(file_path)
                    if agent_info:
                        agents.append(agent_info)
        
        logger.info(f"Найдено агентов: {len(agents)}")
        
        # Регистрируем каждого агента
        registered = []
        failed = []
        
        for agent in agents:
            try:
                logger.info(f"\n{'='*60}")
                logger.info(f"Регистрация агента: {agent['name']}")
                logger.info(f"Файл: {agent['file_path']}")
                logger.info(f"Стадия: {agent['stage']}")
                
                # Проверяем, есть ли уже запись в YDB
                existing_id = ydb_client.get_assistant_id(agent['name'])
                
                # Если найден существующий ассистент - удаляем его
                if existing_id:
                    logger.info(f"⚠️ Найден существующий ассистент '{agent['name']}' с ID: {existing_id}")
                    logger.info("Удаление старого ассистента из Yandex Cloud...")
                    try:
                        old_assistant = langgraph_service.sdk.assistants.get(existing_id)
                        old_assistant.delete()
                        logger.info(f"✅ Старый ассистент удалён из Yandex Cloud")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось удалить старый ассистент из Yandex Cloud: {e}")
                        # Продолжаем работу, возможно ассистент уже был удалён
                    
                    # Удаляем из YDB
                    logger.info("Удаление записи из YDB...")
                    try:
                        ydb_client.delete_assistant_id(agent['name'])
                        logger.info(f"✅ Запись удалена из YDB")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось удалить запись из YDB: {e}")
                
                # Подготавливаем инструменты
                tool_list = []
                if agent['tools']:
                    logger.info(f"Найдены инструменты в агенте: {agent['tools']}")
                    try:
                        from src.agents.tools.service_tools import GetCategories, GetServices, BookTimes, CreateBooking
                        from src.agents.tools.client_records_tools import GetClientRecords
                        from src.agents.tools.cancel_booking_tools import CancelBooking
                        tool_mapping = {
                            'GetCategories': GetCategories,
                            'GetServices': GetServices,
                            'BookTimes': BookTimes,
                            'CreateBooking': CreateBooking,
                            'GetClientRecords': GetClientRecords,
                            'CancelBooking': CancelBooking
                        }
                        tools_classes = [tool_mapping[t] for t in agent['tools'] if t in tool_mapping]
                        if tools_classes:
                            tool_list = [langgraph_service.sdk.tools.function(t) for t in tools_classes]
                            logger.info(f"✅ Инструменты подготовлены: {[t.__name__ for t in tools_classes]}")
                        else:
                            logger.warning(f"⚠️ Не удалось найти классы инструментов для: {agent['tools']}")
                    except Exception as e:
                        logger.warning(f"⚠️ Ошибка при подготовке инструментов: {e}")
                else:
                    logger.info("Инструменты не найдены в агенте")
                
                # Создаем Assistant в Yandex Cloud
                logger.info("Создание нового Assistant в Yandex Cloud...")
                assistant = langgraph_service.create_assistant(
                    instruction=agent['instruction'],
                    tools=tool_list if tool_list else None,
                    name=agent['name']
                )
                
                assistant_id = assistant.id
                logger.info(f"✅ Assistant создан: ID={assistant_id}")
                
                # Проверяем сохранение в YDB (create_assistant автоматически сохраняет)
                saved_id = ydb_client.get_assistant_id(agent['name'])
                if saved_id == assistant_id:
                    logger.info(f"✅ ID сохранён в YDB: {saved_id}")
                else:
                    logger.warning(f"⚠️ Проблема с сохранением в YDB. Ожидалось: {assistant_id}, получено: {saved_id}")
                
                registered.append({
                    'agent': agent,
                    'assistant_id': assistant_id,
                    'status': 'created' if not existing_id else 'recreated'
                })
                
            except Exception as e:
                logger.error(f"❌ Ошибка при регистрации агента {agent['name']}: {e}", exc_info=True)
                failed.append({
                    'agent': agent,
                    'error': str(e)
                })
        
        # Регистрируем StageDetectorAgent отдельно
        logger.info(f"\n{'='*60}")
        logger.info("Регистрация StageDetectorAgent...")
        try:
            stage_detector_file = project_root / "src" / "agents" / "stage_detector_agent.py"
            detector_info = parse_agent_file(stage_detector_file)
            
            if detector_info:
                existing_id = ydb_client.get_assistant_id(detector_info['name'])
                
                # Если найден существующий ассистент - удаляем его
                if existing_id:
                    logger.info(f"⚠️ Найден существующий StageDetectorAgent с ID: {existing_id}")
                    logger.info("Удаление старого ассистента из Yandex Cloud...")
                    try:
                        old_assistant = langgraph_service.sdk.assistants.get(existing_id)
                        old_assistant.delete()
                        logger.info(f"✅ Старый StageDetectorAgent удалён из Yandex Cloud")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось удалить старый ассистент: {e}")
                    
                    # Удаляем из YDB
                    try:
                        ydb_client.delete_assistant_id(detector_info['name'])
                        logger.info(f"✅ Запись удалена из YDB")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось удалить запись из YDB: {e}")
                
                assistant = langgraph_service.create_assistant(
                    instruction=detector_info['instruction'],
                    tools=None,
                    name=detector_info['name']
                )
                logger.info(f"✅ StageDetectorAgent создан: ID={assistant.id}")
                registered.append({
                    'agent': detector_info,
                    'assistant_id': assistant.id,
                    'status': 'created' if not existing_id else 'recreated'
                })
        except Exception as e:
            logger.error(f"❌ Ошибка при регистрации StageDetectorAgent: {e}", exc_info=True)
            failed.append({
                'agent': {'name': 'StageDetectorAgent'},
                'error': str(e)
            })
        
        # Итоги
        logger.info(f"\n{'='*60}")
        logger.info("=== ИТОГИ РЕГИСТРАЦИИ ===")
        logger.info(f"✅ Успешно зарегистрировано: {len([r for r in registered if r['status'] == 'created'])}")
        logger.info(f"🔄 Пересоздано: {len([r for r in registered if r['status'] == 'recreated'])}")
        logger.info(f"⚠️ Уже существовало: {len([r for r in registered if r['status'] == 'exists'])}")
        logger.info(f"❌ Ошибок: {len(failed)}")
        
        if failed:
            logger.info("\nОшибки:")
            for fail in failed:
                logger.error(f"  - {fail['agent'].get('name', 'Unknown')}: {fail['error']}")
        
        logger.info("=== РЕГИСТРАЦИЯ ЗАВЕРШЕНА ===")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Регистрация всех агентов в Yandex Cloud и YDB")
    parser.add_argument('--force', action='store_true', help='Пересоздать даже если агент уже существует')
    args = parser.parse_args()
    
    register_all_agents(force=args.force)

