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
    Используй когда клиент спрашивает "какие у вас есть услуги?" или "что вы предлагаете?"
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
            result += "\n\nДля получения услуг категории используйте GetServices с указанием ID категории."
            
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
    Получить список услуг указанной категории с ценами и ID услуг.
    Используй когда клиент спрашивает "какие виды маникюра?" или "что есть в категории массаж?"
    Сначала вызови GetCategories для получения ID категории.
    """
    
    category_id: str = Field(
        description="ID категории (строка, например '1', '2'). Получи из GetCategories."
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
                service_id = service.get('id', 'Не указан')
                
                service_line = f"  • {name} (ID: {service_id}) - {price} руб."
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


class BookTimes(BaseModel):
    """
    Найти доступные временные слоты для записи на услугу.
    Используй когда клиент выбрал услугу и дату - нужно найти свободное время.
    service_id получай из GetServices (каждая услуга имеет ID: число).
    date в формате YYYY-MM-DD (например "2025-11-12").
    """
    
    service_id: int = Field(
        description="ID услуги (число). Получи из GetServices - каждая услуга имеет формат 'Название (ID: число)'."
    )
    
    date: str = Field(
        description="Дата в формате YYYY-MM-DD (например '2025-11-12'). Преобразуй относительные даты ('сегодня', 'завтра') в этот формат."
    )
    
    master_name: Optional[str] = Field(
        default=None,
        description="Имя мастера (опционально). Если указано - слоты только у этого мастера."
    )
    
    def process(self, thread: Thread) -> str:
        """
        Поиск доступных временных слотов для записи
        
        Returns:
            Отформатированный список доступных временных интервалов
        """
        try:
            import asyncio
            from .yclients_service import YclientsService
            from .book_times_logic import find_best_slots
            
            # Создаем сервис (он сам возьмет переменные окружения)
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
            # Запускаем async функцию синхронно
            result = asyncio.run(
                find_best_slots(
                    yclients_service=yclients_service,
                    service_id=self.service_id,
                    date=self.date,
                    master_name=self.master_name
                )
            )
            
            # Форматируем результат
            if result.get('error'):
                return f"Ошибка: {result['error']}"
            
            service_title = result.get('service_title', 'Услуга')
            master_name = result.get('master_name')
            slots = result.get('slots', [])
            
            if not slots:
                if master_name:
                    return f"К сожалению, на {self.date} у мастера {master_name} нет свободных слотов для услуги '{service_title}'."
                else:
                    return f"К сожалению, на {self.date} нет свободных слотов для услуги '{service_title}'."
            
            # Форматируем список слотов
            slots_text = "\n".join([f"  • {slot}" for slot in slots])
            
            result_text = f"Доступные временные слоты для услуги '{service_title}' на {self.date}:\n\n{slots_text}"
            
            if master_name:
                result_text = f"Доступные временные слоты у мастера {master_name} для услуги '{service_title}' на {self.date}:\n\n{slots_text}"
            
            return result_text
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации BookTimes: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при поиске слотов: {e}", exc_info=True)
            return f"Ошибка при поиске доступных слотов: {str(e)}"


class CreateBooking(BaseModel):
    """
    Создать запись на услугу.
    Используй когда клиент выбрал услугу, дату, время и предоставил свои данные (имя и телефон).
    service_id получай из GetServices (каждая услуга имеет ID: число).
    datetime в формате YYYY-MM-DD HH:MM (например "2025-11-12 14:30").
    """
    
    service_id: int = Field(
        description="ID услуги (число). Получи из GetServices - каждая услуга имеет формат 'Название (ID: число)'."
    )
    
    client_name: str = Field(
        description="Имя клиента"
    )
    
    client_phone: str = Field(
        description="Телефон клиента в любом формате (будет автоматически нормализован)"
    )
    
    datetime: str = Field(
        description="Дата и время записи в формате YYYY-MM-DD HH:MM (например '2025-11-12 14:30') или YYYY-MM-DDTHH:MM"
    )
    
    master_name: Optional[str] = Field(
        default=None,
        description="Имя мастера (опционально). Если указано - запись только к этому мастеру. НЕ УКАЗЫВАЙ если клиент не просил конкретного мастера."
    )
    
    def process(self, thread: Thread) -> str:
        """
        Создание записи на услугу
        
        Returns:
            Сообщение о результате создания записи
        """
        try:
            import asyncio
            from .yclients_service import YclientsService
            from .create_booking_logic import create_booking_logic
            
            # Создаем сервис (он сам возьмет переменные окружения)
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
            # Запускаем async функцию синхронно
            result = asyncio.run(
                create_booking_logic(
                    yclients_service=yclients_service,
                    service_id=self.service_id,
                    client_name=self.client_name,
                    client_phone=self.client_phone,
                    datetime=self.datetime,
                    master_name=self.master_name
                )
            )
            
            # Возвращаем сообщение из результата
            return result.get('message', 'Неизвестная ошибка')
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации CreateBooking: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при создании записи: {e}", exc_info=True)
            return f"Ошибка при создании записи: {str(e)}"


class FindMasterByService(BaseModel):
    """
    Найти мастера по имени и услуге.
    Используй когда клиент хочет записаться к конкретному мастеру на конкретную услугу.
    Имя мастера и название услуги могут быть неточными - инструмент найдет похожие варианты.
    Например: "хочу записаться к Анне на маникюр" -> найдет мастера Анну, которая делает маникюр.
    """
    
    master_name: str = Field(
        description="Имя мастера (может быть неточным, например 'Аня', 'Анна', 'Аннушка')"
    )
    
    service_name: str = Field(
        description="Название услуги (может быть неточным, например 'маникюр', 'массаж', 'педикюр')"
    )
    
    def process(self, thread: Thread) -> str:
        """
        Поиск мастера по имени и услуге
        
        Returns:
            Отформатированная информация о мастере и его услугах
        """
        try:
            import asyncio
            from .yclients_service import YclientsService
            from .find_master_by_service_logic import find_master_by_service_logic
            
            # Создаем сервис (он сам возьмет переменные окружения)
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
            # Запускаем async функцию синхронно
            result = asyncio.run(
                find_master_by_service_logic(
                    yclients_service=yclients_service,
                    master_name=self.master_name,
                    service_name=self.service_name
                )
            )
            
            # Форматируем результат
            if not result.get('success'):
                error = result.get('error', 'Неизвестная ошибка')
                return f"Ошибка: {error}"
            
            master = result.get('master', {})
            master_name_result = master.get('name', '')
            master_id = master.get('id', '')
            position_title = master.get('position_title', '')
            
            services = result.get('services', [])
            
            if not services:
                return f"Мастер {master_name_result} найден, но у него нет доступных услуг."
            
            # Форматируем список услуг
            services_text = "\n".join([
                f"  • {service['title']} (ID: {service['id']})"
                for service in services
            ])
            
            result_text = (
                f"Найден мастер: {master_name_result}"
            )
            
            if position_title:
                result_text += f" ({position_title})"
            
            result_text += f"\nID мастера: {master_id}\n\n"
            result_text += f"Доступные услуги:\n{services_text}"
            
            return result_text
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации FindMasterByService: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при поиске мастера: {e}", exc_info=True)
            return f"Ошибка при поиске мастера: {str(e)}"

