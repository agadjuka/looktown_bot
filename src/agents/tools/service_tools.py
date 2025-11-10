"""
Инструменты для работы с каталогом услуг
"""
import json
from typing import Optional
from pydantic import BaseModel, Field
from yandex_cloud_ml_sdk._threads.thread import Thread

# Импорты
from .services_data_loader import _data_loader

try:
    from ..services.logger_service import logger
except ImportError:
    # Простой logger для случаев, когда logger_service недоступен
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class GetCategories(BaseModel):
    """
    Получить список всех категорий услуг с их ID.
    
    Используй этот инструмент, когда:
    - Клиент спрашивает "какие у вас есть услуги?" или "что вы предлагаете?"
    - Клиент хочет узнать, какие категории услуг доступны в салоне
    - Нужно показать клиенту полный список категорий (Маникюр, Педикюр, Массаж и т.д.)
    
    Инструмент возвращает список всех категорий с их ID, которые затем можно использовать
    для получения конкретных услуг через инструмент GetServices.
    """
    
    def process(self, thread: Thread) -> str:
        """
        Получение списка всех категорий услуг
        
        Returns:
            Отформатированный список категорий с ID
        """
        try:
            data = _data_loader.load_data()
            
            if not data:
                return "Категории услуг не найдены"
            
            categories = []
            for cat_id, cat_data in sorted(data.items(), key=lambda x: int(x[0])):
                category_name = cat_data.get('category_name', 'Неизвестно')
                categories.append(f"{cat_id}. {category_name}")
            
            result = "Доступные категории услуг:\n\n" + "\n".join(categories)
            result += "\n\nДля получения услуг категории используйте инструмент GetServices с указанием ID категории."
            
            return result
            
        except FileNotFoundError as e:
            logger.error(f"Файл с услугами не найден: {e}")
            return "Файл с данными об услугах не найден"
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            return "Ошибка при чтении данных об услугах"
        except Exception as e:
            logger.error(f"Ошибка при получении категорий: {e}")
            return f"Ошибка при получении категорий: {str(e)}"


class GetServices(BaseModel):
    """
    Получить список всех услуг указанной категории с ценами и уровнями мастеров.
    
    Используй этот инструмент, когда:
    - Клиент спрашивает "какие виды маникюра у вас есть?" или "что есть в категории массаж?"
    - Клиент хочет узнать конкретные услуги внутри категории
    - Нужно показать клиенту список услуг с ценами для выбора
    
    Сначала используй GetCategories, чтобы получить ID нужной категории, затем вызывай
    этот инструмент с указанием category_id.
    """
    
    category_id: str = Field(
        description="ID категории услуг (например, '1' для Маникюра, '2' для Педикюра, '3' для Услуг для мужчин). "
                   "Обязательно сначала вызови GetCategories, чтобы получить актуальный список всех категорий с их ID. "
                   "ID всегда является строкой (например, '1', '2', '13')."
    )
    
    def process(self, thread: Thread) -> str:
        """
        Получение списка услуг указанной категории
        
        Args:
            category_id: ID категории из списка категорий
            
        Returns:
            Отформатированный список услуг категории
        """
        try:
            data = _data_loader.load_data()
            
            if not data:
                return "Данные об услугах не найдены"
            
            # Получаем категорию по ID
            category = data.get(self.category_id)
            if not category:
                available_ids = ", ".join(sorted(data.keys(), key=int))
                return (
                    f"Категория с ID '{self.category_id}' не найдена.\n"
                    f"Доступные ID категорий: {available_ids}\n"
                    f"Используйте GetCategories для получения полного списка категорий."
                )
            
            category_name = category.get('category_name', 'Неизвестно')
            services = category.get('services', [])
            
            if not services:
                return f"В категории '{category_name}' нет доступных услуг"
            
            # Форматируем услуги
            result_lines = [f"Услуги категории '{category_name}':\n"]
            
            for service in services:
                name = service.get('name', 'Неизвестно')
                price = service.get('prices', 'Не указана')
                master_level = service.get('master_level')
                
                service_line = f"  • {name} - {price} руб."
                if master_level:
                    service_line += f" ({master_level})"
                
                result_lines.append(service_line)
            
            return "\n".join(result_lines)
            
        except FileNotFoundError as e:
            logger.error(f"Файл с услугами не найден: {e}")
            return "Файл с данными об услугах не найден"
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            return "Ошибка при чтении данных об услугах"
        except Exception as e:
            logger.error(f"Ошибка при получении услуг: {e}")
            return f"Ошибка при получении услуг: {str(e)}"

