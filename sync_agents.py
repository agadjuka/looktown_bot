"""
Скрипт для синхронизации инструкций всех агентов с Yandex Cloud
Обновляет инструкции всех ассистентов в Yandex Cloud согласно файлам агентов
"""
import os
import sys
import re
import logging
import json
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
        
        return {
            'file_path': str(file_path.relative_to(project_root)),
            'class_name': class_name,
            'name': agent_name,
            'instruction': instruction,
            'full_path': str(file_path)
        }
    except Exception as e:
        logger.error(f"Ошибка при парсинге {file_path}: {e}")
        return None


def sync_all_agents():
    """Синхронизация всех агентов с Yandex Cloud"""
    logger.info("=== НАЧАЛО СИНХРОНИЗАЦИИ АГЕНТОВ ===")
    
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
        
        # Синхронизируем каждого агента
        synced = []
        failed = []
        
        for agent in agents:
            try:
                logger.info(f"\n{'='*60}")
                logger.info(f"Синхронизация агента: {agent['name']}")
                logger.info(f"Файл: {agent['file_path']}")
                
                # Получаем ID из YDB
                assistant_id = ydb_client.get_assistant_id(agent['name'])
                if not assistant_id:
                    logger.warning(f"⚠️ Агент '{agent['name']}' не найден в YDB. Пропускаем.")
                    failed.append({
                        'agent': agent,
                        'error': 'Не найден в YDB'
                    })
                    continue
                
                logger.info(f"Найден ID в YDB: {assistant_id}")
                
                # Получаем ассистента из Yandex Cloud
                try:
                    assistant = langgraph_service.sdk.assistants.get(assistant_id)
                    logger.info(f"✅ Ассистент загружен из Yandex Cloud")
                except Exception as e:
                    logger.error(f"❌ Не удалось загрузить ассистента: {e}")
                    failed.append({
                        'agent': agent,
                        'error': f'Не удалось загрузить: {e}'
                    })
                    continue
                
                # Обновляем инструкцию
                logger.info("Обновление инструкции...")
                try:
                    assistant.update(instruction=agent['instruction'])
                    logger.info(f"✅ Инструкция обновлена в Yandex Cloud")
                    synced.append({
                        'agent': agent,
                        'assistant_id': assistant_id,
                        'status': 'synced'
                    })
                except Exception as e:
                    logger.error(f"❌ Ошибка обновления инструкции: {e}", exc_info=True)
                    failed.append({
                        'agent': agent,
                        'error': f'Ошибка обновления: {e}'
                    })
                
            except Exception as e:
                logger.error(f"❌ Ошибка при синхронизации агента {agent['name']}: {e}", exc_info=True)
                failed.append({
                    'agent': agent,
                    'error': str(e)
                })
        
        # Синхронизируем StageDetectorAgent отдельно
        logger.info(f"\n{'='*60}")
        logger.info("Синхронизация StageDetectorAgent...")
        try:
            stage_detector_file = project_root / "src" / "agents" / "stage_detector_agent.py"
            detector_info = parse_agent_file(stage_detector_file)
            
            if detector_info:
                assistant_id = ydb_client.get_assistant_id(detector_info['name'])
                if assistant_id:
                    assistant = langgraph_service.sdk.assistants.get(assistant_id)
                    assistant.update(instruction=detector_info['instruction'])
                    logger.info(f"✅ StageDetectorAgent синхронизирован")
                    synced.append({
                        'agent': detector_info,
                        'assistant_id': assistant_id,
                        'status': 'synced'
                    })
                else:
                    logger.warning(f"⚠️ StageDetectorAgent не найден в YDB")
        except Exception as e:
            logger.error(f"❌ Ошибка при синхронизации StageDetectorAgent: {e}", exc_info=True)
            failed.append({
                'agent': {'name': 'StageDetectorAgent'},
                'error': str(e)
            })
        
        # Итоги
        logger.info(f"\n{'='*60}")
        logger.info("=== ИТОГИ СИНХРОНИЗАЦИИ ===")
        logger.info(f"✅ Успешно синхронизировано: {len(synced)}")
        logger.info(f"❌ Ошибок: {len(failed)}")
        
        if failed:
            logger.info("\nОшибки:")
            for fail in failed:
                logger.error(f"  - {fail['agent'].get('name', 'Unknown')}: {fail['error']}")
        
        logger.info("=== СИНХРОНИЗАЦИЯ ЗАВЕРШЕНА ===")
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    sync_all_agents()


