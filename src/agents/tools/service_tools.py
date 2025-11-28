"""
Инструменты для работы с каталогом услуг
"""
import json
from datetime import datetime
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
    """
    
    category_id: str = Field(
        description="ID категории (строка). Доступные категории: '1' - Маникюр, '2' - Педикюр, '3' - Услуги для мужчин, '4' - Брови, '5' - Ресницы, '6' - Макияж, '7' - Парикмахерские услуги, '8' - Пирсинг, '9' - Лазерная эпиляция, '10' - Косметология, '11' - Депиляция, '12' - Массаж, '13' - LOOKTOWN SPA."
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


class FindSlots(BaseModel):
    """
    Найти доступные временные слоты для услуги с фильтрацией по периоду времени.
    Используй когда клиент хочет найти время в определенный период (утром, днем, вечером) 
    или в определенном интервале дат. Этот инструмент может искать слоты на несколько дней вперед 
    и фильтровать по времени суток. Также может искать слоты на конкретную дату.
    Если time_period не указан, инструмент найдет ближайшие доступные слоты без фильтрации по времени.
    """
    
    service_id: int = Field(
        description="ID услуги (число, обязательное поле). Получи из GetServices - каждая услуга имеет формат 'Название (ID: число)'."
    )
    
    time_period: Optional[str] = Field(
        default=None,
        description="Период времени (необязательное поле). Если не указан, будут найдены ближайшие доступные слоты без фильтрации по времени. Поддерживаемые форматы: 'morning' (9:00-11:00), 'day' (11:00-17:00), 'evening' (17:00-22:00); конкретное время '16:00' или '16.00' (слот 30 минут); интервал '16:00-19:00' или '16.00-19.00'; 'before 11:00' (до 11:00); 'after 16:00' (после 16:00). Используй когда клиент просит время в определенный период или интервал."
    )
    
    master_name: Optional[str] = Field(
        default=None,
        description="Имя мастера (необязательное поле). Заполняй только если клиент хочет записаться к конкретному мастеру. Инструмент найдет мастера по вариациям имени (например, 'Анна' найдет 'Аня', 'Аннушка')."
    )
    
    master_id: Optional[int] = Field(
        default=None,
        description="ID мастера (необязательное поле). Заполняй только если знаешь точный ID мастера. Если указан master_id, то master_name игнорируется."
    )
    
    date: Optional[str] = Field(
        default=None,
        description="Конкретная дата (необязательное поле). Формат: 'YYYY-MM-DD' (например, '2025-01-15'). Заполняй только если клиент указал конкретную дату. Если клиент просит найти ближайшую дату или справшивает когда есть свободые слоты - оставь пустым."
    )
    
    date_range: Optional[str] = Field(
        default=None,
        description="Интервал дат (необязательное поле). Формат: 'YYYY-MM-DD:YYYY-MM-DD' (например, '2025-01-11:2025-01-16'). Заполняй только если клиент указал конкретный интервал дат и не указана конкретная дата. Если не указан, инструмент будет искать с текущей даты до 10 дней вперед, пока не найдет 3 дня с доступными слотами."
    )
    
    def process(self, thread: Thread) -> str:
        """
        Поиск доступных временных слотов с фильтрацией по периоду времени
        
        Returns:
            Отформатированный список доступных временных интервалов по датам
        """
        try:
            import asyncio
            from .yclients_service import YclientsService
            from .find_slots_logic import find_slots_by_period
            
            # Создаем сервис (он сам возьмет переменные окружения)
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
            # Запускаем async функцию синхронно
            result = asyncio.run(
                find_slots_by_period(
                    yclients_service=yclients_service,
                    service_id=self.service_id,
                    time_period=self.time_period or "",
                    master_name=self.master_name,
                    master_id=self.master_id,
                    date=self.date,
                    date_range=self.date_range
                )
            )
            
            # Форматируем результат
            if result.get('error'):
                return f"Ошибка: {result['error']}"
            
            service_title = result.get('service_title', 'Услуга')
            time_period = result.get('time_period', '')
            master_name = result.get('master_name')
            results = result.get('results', [])
            
            if not results:
                # Форматируем название периода для вывода
                if time_period:
                    period_display = self._format_time_period_display(time_period)
                    period_text = f" {period_display}"
                else:
                    period_text = ""
                
                if master_name:
                    if self.date:
                        return f"К сожалению, у мастера {master_name} нет свободных слотов{period_text} для услуги '{service_title}' на {self.date}."
                    elif self.date_range:
                        return f"К сожалению, у мастера {master_name} нет свободных слотов{period_text} для услуги '{service_title}' в указанный период."
                    else:
                        return f"К сожалению, у мастера {master_name} нет свободных слотов{period_text} для услуги '{service_title}' в ближайшие дни."
                else:
                    if self.date:
                        return f"К сожалению, нет свободных слотов{period_text} для услуги '{service_title}' на {self.date}."
                    elif self.date_range:
                        return f"К сожалению, нет свободных слотов{period_text} для услуги '{service_title}' в указанный период."
                    else:
                        return f"К сожалению, нет свободных слотов{period_text} для услуги '{service_title}' в ближайшие дни."
            
            # Форматируем список результатов по датам
            if time_period:
                period_display = self._format_time_period_display(time_period)
                period_text = f" {period_display}"
            else:
                period_text = ""
            
            result_lines = []
            if master_name:
                result_lines.append(f"Доступные слоты{period_text} у мастера {master_name} для услуги '{service_title}':\n")
            else:
                result_lines.append(f"Доступные слоты{period_text} для услуги '{service_title}':\n")
            
            for day_result in results:
                date = day_result['date']
                slots = day_result['slots']
                
                # Форматируем дату для вывода
                try:
                    date_obj = datetime.strptime(date, "%Y-%m-%d")
                    formatted_date = date_obj.strftime("%d.%m.%Y")
                except:
                    formatted_date = date
                
                slots_text = " | ".join(slots)
                result_lines.append(f"  {formatted_date}: {slots_text}")
            
            return "\n".join(result_lines)
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации FindSlots: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при поиске слотов: {e}", exc_info=True)
            return f"Ошибка при поиске доступных слотов: {str(e)}"
    
    def _format_time_period_display(self, time_period: str) -> str:
        """Форматирует период времени для отображения пользователю"""
        time_period_lower = time_period.strip().lower()
        
        # Предопределенные периоды
        period_names = {
            'morning': 'утром',
            'day': 'днем',
            'evening': 'вечером'
        }
        
        if time_period_lower in period_names:
            return period_names[time_period_lower]
        
        # "before HH:MM"
        if time_period_lower.startswith("before "):
            time_str = time_period[7:].strip()
            return f"до {time_str}"
        
        # "after HH:MM"
        if time_period_lower.startswith("after "):
            time_str = time_period[6:].strip()
            return f"после {time_str}"
        
        # Интервал "HH:MM-HH:MM"
        if '-' in time_period:
            return f"в период {time_period}"
        
        # Конкретное время "HH:MM"
        return f"около {time_period}"


class CreateBooking(BaseModel):
    """
    Создать запись на услугу.
    Используй когда клиент выбрал услугу, дату, время и предоставил свои данные (имя и телефон).
    
    Откуда брать данные для полей:
    - service_id: из GetServices (каждая услуга имеет ID: число)
    - client_name: из сообщений клиента в диалоге (Шаг 6 сбора данных)
    - client_phone: из сообщений клиента в диалоге (Шаг 6 сбора данных)
    - datetime: собери из даты (Шаг 3) и времени (Шаг 5, выбранного клиентом из FindSlots), формат YYYY-MM-DD HH:MM (например "2025-11-12 14:30")
    - master_name: из FindSlots (если был указан мастер) или из сообщений клиента (если клиент просил конкретного мастера), опционально
    """
    
    service_id: int = Field(
        description="ID услуги (число). Получи из GetServices - каждая услуга имеет формат 'Название (ID: число)'."
    )
    
    client_name: str = Field(
        description="Имя клиента. Получи из сообщений клиента в диалоге, когда он предоставляет свои данные (Шаг 6 сбора данных)."
    )
    
    client_phone: str = Field(
        description="Телефон клиента в любом формате (будет автоматически нормализован). Получи из сообщений клиента в диалоге, когда он предоставляет свои данные (Шаг 6 сбора данных)."
    )
    
    datetime: str = Field(
        description="Дата и время записи в формате YYYY-MM-DD HH:MM (например '2025-11-12 14:30') или YYYY-MM-DDTHH:MM. Собери из: дата из Шага 3 (когда клиент выбрал дату) и время из Шага 5 (когда клиент выбрал конкретное время из доступных слотов FindSlots)."
    )
    
    master_name: Optional[str] = Field(
        default=None,
        description="Имя мастера (опционально). Получи из FindSlots (если клиент выбирал время у конкретного мастера) или из сообщений клиента (если клиент явно просил записаться к конкретному мастеру). НЕ УКАЗЫВАЙ если клиент не просил конкретного мастера."
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


class ViewService(BaseModel):
    """
    Получить детальную информацию об услуге по её ID.
    Используй когда нужно узнать подробности об услуге: название, цену, продолжительность, список мастеров.
    service_id получай из GetServices (каждая услуга имеет ID: число).
    """
    
    service_id: int = Field(
        description="ID услуги (число). Получи из GetServices - каждая услуга имеет формат 'Название (ID: число)'."
    )
    
    def process(self, thread: Thread) -> str:
        """
        Получение детальной информации об услуге
        
        Returns:
            Отформатированная информация об услуге
        """
        try:
            import asyncio
            from .yclients_service import YclientsService
            from .view_service_logic import view_service_logic
            
            # Создаем сервис (он сам возьмет переменные окружения)
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
            # Запускаем async функцию синхронно
            result = asyncio.run(
                view_service_logic(
                    yclients_service=yclients_service,
                    service_id=self.service_id
                )
            )
            
            # Форматируем результат
            if not result.get('success'):
                error = result.get('error', 'Неизвестная ошибка')
                message = result.get('message', '')
                status = result.get('status')
                
                if error == 'bad_service_id':
                    return f"Ошибка: {message}"
                elif error == 'yclients_http_error':
                    return f"Ошибка при обращении к API Yclients (HTTP {status}): {message}"
                else:
                    if message:
                        return f"Ошибка: {error}. {message}"
                    return f"Ошибка: {error}"
            
            service = result.get('service', {})
            
            # Формируем отформатированный ответ
            result_lines = []
            
            # Название услуги
            title = service.get('title', 'Неизвестно')
            result_lines.append(f"Услуга: {title}")
            result_lines.append(f"ID услуги: {service.get('id', 'Не указан')}")
            
            # Категория
            category_id = service.get('category_id')
            if category_id:
                result_lines.append(f"ID категории: {category_id}")
            
            # Продолжительность
            duration_sec = service.get('duration_sec')
            if duration_sec:
                duration_min = duration_sec // 60
                result_lines.append(f"Продолжительность: {duration_min} минут")
            
            # Цена
            price_min = service.get('price_min')
            price_max = service.get('price_max')
            if price_min or price_max:
                if price_min == price_max:
                    result_lines.append(f"Цена: {price_min} руб.")
                else:
                    result_lines.append(f"Цена: {price_min or 'от'} - {price_max or 'до'} руб.")
            
            # Статус
            active = service.get('active', True)
            result_lines.append(f"Статус: {'Активна' if active else 'Неактивна'}")
            
            # Комментарий
            comment = service.get('comment')
            if comment:
                result_lines.append(f"\nОписание:\n{comment}")
            
            # Мастера
            staff = service.get('staff', [])
            if staff:
                result_lines.append(f"\nМастера ({len(staff)}):")
                for master in staff:
                    master_name = master.get('name', 'Неизвестно')
                    master_id = master.get('id', 'Не указан')
                    result_lines.append(f"  • {master_name} (ID: {master_id})")
            else:
                result_lines.append("\nМастера не найдены")
            
            return "\n".join(result_lines)
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации ViewService: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при получении информации об услуге: {e}", exc_info=True)
            return f"Ошибка при получении информации об услуге: {str(e)}"

