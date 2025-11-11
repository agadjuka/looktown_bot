"""
Логика для создания записи на услугу
Адаптировано из Cloud Function
"""
import asyncio
from typing import Optional, Tuple, List
from .yclients_service import YclientsService, Master
from .phone_utils import normalize_phone


def _normalize_name(name: str) -> str:
    """
    Нормализует имя для сравнения: приводит к нижнему регистру и убирает пробелы.
    
    Args:
        name: Имя для нормализации
        
    Returns:
        str: Нормализованное имя
    """
    if not name:
        return ""
    return name.lower().strip()


def _get_name_variants(name: str) -> List[str]:
    """
    Генерирует варианты имени для более гибкого поиска.
    Например: "Анна" -> ["анна", "аня", "аннушка"]
    
    Args:
        name: Исходное имя
        
    Returns:
        List[str]: Список вариантов имени
    """
    normalized = _normalize_name(name)
    variants = [normalized]
    
    # Словарь распространенных сокращений и вариантов русских имен
    name_mappings = {
        "анна": ["аня", "аннушка", "анюта"],
        "елена": ["лена", "лёна", "елена"],
        "екатерина": ["катя", "катюша", "катерина"],
        "мария": ["маша", "маруся", "мария"],
        "наталья": ["наташа", "наталия", "наталья"],
        "ольга": ["оля", "ольга"],
        "татьяна": ["таня", "татьяна"],
        "юлия": ["юля", "юлия"],
        "александра": ["саша", "сашенька", "александра"],
        "вероника": ["ника", "вероника"],
        "софия": ["софья", "софия", "сона"],
        "полина": ["поля", "полина"],
        "анастасия": ["настя", "анастасия"],
        "константин": ["костя", "константин"],
    }
    
    # Проверяем, есть ли варианты для этого имени
    if normalized in name_mappings:
        variants.extend(name_mappings[normalized])
    
    return variants


def _find_master_by_name(masters: List[Master], search_name: str) -> Optional[Master]:
    """
    Находит мастера по имени с учетом вариаций и регистра.
    
    Args:
        masters: Список мастеров
        search_name: Имя для поиска
        
    Returns:
        Optional[Master]: Найденный мастер или None
    """
    if not search_name or not masters:
        return None
    
    # Генерируем варианты искомого имени
    search_variants = _get_name_variants(search_name)
    
    # Исключаем "Лист ожидания"
    valid_masters = [m for m in masters if m.name and m.name != "Лист ожидания"]
    
    # Ищем точное совпадение (после нормализации)
    normalized_search = _normalize_name(search_name)
    for master in valid_masters:
        if not master.name:
            continue
        
        normalized_master_name = _normalize_name(master.name)
        
        # Точное совпадение
        if normalized_master_name == normalized_search:
            return master
        
        # Проверяем варианты
        master_variants = _get_name_variants(master.name)
        if any(variant in search_variants for variant in master_variants):
            return master
        
        # Проверяем, содержит ли имя мастера искомое имя или наоборот
        if normalized_search in normalized_master_name or normalized_master_name in normalized_search:
            return master
    
    return None


def _normalize_time(time_str: str) -> str:
    """
    Нормализует время, убирая ведущие нули
    '09:00' -> '9:00'
    '9:00' -> '9:00'
    
    Args:
        time_str: Время в формате HH:MM или H:MM
        
    Returns:
        str: Нормализованное время без ведущих нулей
    """
    if ':' not in time_str:
        return time_str
    
    parts = time_str.split(':')
    hour = int(parts[0])  # Убираем ведущие нули через конвертацию в int
    minute = parts[1]
    
    return f"{hour}:{minute}"


def _parse_datetime(datetime_str: str) -> Tuple[str, str]:
    """
    Разбирает строку datetime на дату и время
    
    Args:
        datetime_str: Строка с датой и временем
        
    Returns:
        Tuple[str, str]: (дата в формате YYYY-MM-DD, время в формате H:MM без ведущих нулей)
    """
    # Поддерживаем форматы: "2025-11-08 14:30" или "2025-11-08T14:30"
    datetime_str = datetime_str.strip()
    
    if 'T' in datetime_str:
        parts = datetime_str.split('T')
    elif ' ' in datetime_str:
        parts = datetime_str.split(' ')
    else:
        raise ValueError(f"Неверный формат datetime: {datetime_str}")
    
    date = parts[0]
    time = parts[1] if len(parts) > 1 else ""
    
    # Убираем секунды, если есть
    if ':' in time:
        time_parts = time.split(':')
        time = f"{time_parts[0]}:{time_parts[1]}"
    
    # Нормализуем время (убираем ведущие нули)
    time = _normalize_time(time)
    
    return date, time


async def _find_available_master(
    yclients_service: YclientsService,
    service_id: int,
    date: str,
    target_time: str,
    valid_masters: list
) -> Optional[Tuple[int, str]]:
    """
    Находит мастера, у которого есть свободный слот в указанное время
    
    Args:
        yclients_service: Сервис для работы с API
        service_id: ID услуги
        date: Дата в формате YYYY-MM-DD
        target_time: Целевое время в формате HH:MM
        valid_masters: Список валидных мастеров
        
    Returns:
        Optional[Tuple[int, str]]: (master_id, master_name) или None если не найдено
    """
    master_ids = [master.id for master in valid_masters]
    
    # Параллельно запрашиваем слоты для всех мастеров
    tasks = [
        yclients_service.get_book_times(
            master_id=master_id,
            date=date,
            service_id=service_id
        )
        for master_id in master_ids
    ]
    
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Нормализуем целевое время для корректного сравнения
    normalized_target_time = _normalize_time(target_time)
    
    # Проверяем каждого мастера на наличие нужного времени
    for master, response in zip(valid_masters, responses):
        if isinstance(response, Exception):
            continue
        
        # Нормализуем все времена из слотов для корректного сравнения
        available_times = [_normalize_time(slot.time) for slot in response.data]
        
        # Если найден слот с нужным временем, берем этого мастера
        if normalized_target_time in available_times:
            return (master.id, master.name)
    
    return None


async def create_booking_logic(
    yclients_service: YclientsService,
    service_id: int,
    client_name: str,
    client_phone: str,
    datetime: str,
    master_name: Optional[str] = None
) -> dict:
    """
    Основная логика создания записи на услугу
    
    Args:
        yclients_service: Сервис для работы с API
        service_id: ID услуги
        client_name: Имя клиента
        client_phone: Телефон клиента
        datetime: Дата и время записи в формате YYYY-MM-DD HH:MM или YYYY-MM-DDTHH:MM
        master_name: Имя мастера (опционально)
        
    Returns:
        dict: Результат создания записи с полями success, message, master_name, datetime, service_title, price (если доступна)
    """
    try:
        # 0. Нормализуем номер телефона к формату +7XXXXXXXXXX
        try:
            normalized_phone = normalize_phone(client_phone)
        except ValueError as e:
            return {
                "success": False,
                "message": f"Ошибка в номере телефона: {str(e)}"
            }
        
        # 1. Получаем детали услуги (мастера и продолжительность)
        service_details = await yclients_service.get_service_details(service_id)
        
        service_title = service_details.get_title()
        seance_length = service_details.duration  # API уже возвращает в секундах
        
        # Проверяем, что это не "Лист ожидания"
        if service_title == "Лист ожидания":
            return {
                "success": False,
                "message": "Запись на 'Лист ожидания' невозможна"
            }
        
        # Фильтруем мастеров, исключая "Лист ожидания"
        all_masters = service_details.staff
        valid_masters = [
            master for master in all_masters
            if master.name != "Лист ожидания"
        ]
        
        # Если указан master_name, ищем конкретного мастера
        if master_name:
            found_master = _find_master_by_name(valid_masters, master_name)
            
            if not found_master:
                return {
                    "success": False,
                    "message": f"Мастер с именем '{master_name}' не найден для данной услуги",
                    "service_title": service_title
                }
            
            valid_masters = [found_master]
        
        if not valid_masters:
            return {
                "success": False,
                "message": "Нет доступных мастеров для данной услуги"
            }
        
        # 2. Разбираем дату и время
        date, target_time = _parse_datetime(datetime)
        
        # 3. Находим мастера с доступным слотом
        master_info = await _find_available_master(
            yclients_service=yclients_service,
            service_id=service_id,
            date=date,
            target_time=target_time,
            valid_masters=valid_masters
        )
        
        if not master_info:
            return {
                "success": False,
                "message": f"К сожалению, на {datetime} нет свободных мастеров для услуги '{service_title}'",
                "service_title": service_title,
                "datetime": datetime
            }
        
        master_id, master_name_result = master_info
        
        # 4. Создаем запись
        booking_response = await yclients_service.create_booking(
            staff_id=master_id,
            service_id=service_id,
            client_name=client_name,
            client_phone=normalized_phone,  # Используем нормализованный номер
            datetime=datetime,
            seance_length=seance_length
        )
        
        if not booking_response.get("success"):
            error_msg = booking_response.get("error", "Неизвестная ошибка")
            return {
                "success": False,
                "message": f"Ошибка при создании записи: {error_msg}",
                "service_title": service_title
            }
        
        # 5. Извлекаем цену и другие данные из ответа API
        price = None
        response_data = booking_response.get("data", {})
        
        # Структура ответа: data.data.services[0].cost
        if isinstance(response_data, dict):
            # Проверяем вложенную структуру data.data
            nested_data = response_data.get("data", {})
            if isinstance(nested_data, dict):
                # Ищем цену в services[0].cost
                services = nested_data.get("services", [])
                if services and isinstance(services, list) and len(services) > 0:
                    first_service = services[0]
                    if isinstance(first_service, dict):
                        price = first_service.get("cost") or first_service.get("price")
        
        # 6. Форматируем дату и время в удобный формат
        def format_datetime_russian(datetime_str: str) -> str:
            """Форматирует дату и время в русский формат: '13 ноября 2025, 12:00'"""
            try:
                from datetime import datetime
                
                # Парсим дату и время
                date_part = ""
                time_part = ""
                
                if 'T' in datetime_str:
                    parts = datetime_str.split('T', 1)
                    date_part = parts[0]
                    if len(parts) > 1:
                        # Убираем часовой пояс и секунды
                        time_str = parts[1]
                        if '+' in time_str:
                            time_str = time_str.split('+')[0]
                        elif '-' in time_str and len(time_str.split('-')) > 3:
                            # Проверяем, не является ли последняя часть часовым поясом
                            time_parts = time_str.rsplit('-', 1)
                            if ':' in time_parts[-1]:
                                time_str = time_parts[0]
                        time_parts = time_str.split(':')
                        if len(time_parts) >= 2:
                            time_part = f"{time_parts[0]}:{time_parts[1]}"
                elif ' ' in datetime_str:
                    parts = datetime_str.split(' ', 1)
                    date_part = parts[0]
                    if len(parts) > 1:
                        time_str = parts[1]
                        # Убираем секунды, если есть
                        time_parts = time_str.split(':')
                        if len(time_parts) >= 2:
                            time_part = f"{time_parts[0]}:{time_parts[1]}"
                else:
                    date_part = datetime_str
                
                # Парсим дату
                date_obj = datetime.strptime(date_part, "%Y-%m-%d")
                
                # Названия месяцев в родительном падеже
                months_ru = {
                    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
                    5: "мая", 6: "июня", 7: "июля", 8: "августа",
                    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
                }
                
                day = date_obj.day
                month = months_ru[date_obj.month]
                year = date_obj.year
                
                # Форматируем дату: "13 ноября 2025"
                date_formatted = f"{day} {month} {year}"
                
                # Форматируем время (убираем ведущие нули)
                if time_part:
                    time_parts = time_part.split(':')
                    if len(time_parts) >= 2:
                        hours = str(int(time_parts[0]))  # Убираем ведущие нули
                        minutes = time_parts[1]
                        time_formatted = f"{hours}:{minutes}"
                        return f"{date_formatted}, {time_formatted}"
                
                return date_formatted
            except Exception as e:
                # В случае ошибки возвращаем исходную строку
                return datetime_str
        
        formatted_datetime = format_datetime_russian(datetime)
        
        # 7. Формируем успешный ответ с полной информацией
        message_parts = [
            f"{client_name}, успешно записано на услугу",
            f"{service_title}",
            f"{formatted_datetime}",
            f"к мастеру {master_name_result}"
        ]
        
        if price is not None:
            message_parts.append(f"Цена: {price} руб.")
        
        message = ". ".join(message_parts) + "."
        
        result = {
            "success": True,
            "message": message,
            "master_name": master_name_result,
            "datetime": datetime,
            "service_title": service_title,
            "client_name": client_name
        }
        
        # Добавляем цену, если она была найдена
        if price is not None:
            result["price"] = price
        
        return result
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Ошибка при обработке запроса: {str(e)}"
        }

