"""
Логика для поиска доступных слотов
Адаптировано из Cloud Function
"""
import asyncio
from typing import List, Dict, Optional
from .yclients_service import YclientsService, Master


def _normalize_name(name: str) -> str:
    """Нормализует имя для сравнения: приводит к нижнему регистру и убирает пробелы."""
    if not name:
        return ""
    return name.lower().strip()


def _get_name_variants(name: str) -> List[str]:
    """Генерирует варианты имени для более гибкого поиска."""
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
    
    if normalized in name_mappings:
        variants.extend(name_mappings[normalized])
    
    return variants


def _find_master_by_name(masters: List[Master], search_name: str) -> Optional[Master]:
    """Находит мастера по имени с учетом вариаций и регистра."""
    if not search_name or not masters:
        return None
    
    search_variants = _get_name_variants(search_name)
    valid_masters = [m for m in masters if m.name and m.name != "Лист ожидания"]
    
    normalized_search = _normalize_name(search_name)
    for master in valid_masters:
        if not master.name:
            continue
        
        normalized_master_name = _normalize_name(master.name)
        
        if normalized_master_name == normalized_search:
            return master
        
        master_variants = _get_name_variants(master.name)
        if any(variant in search_variants for variant in master_variants):
            return master
        
        if normalized_search in normalized_master_name or normalized_master_name in normalized_search:
            return master
    
    return None


def _get_start_time_minutes(interval: str) -> int:
    """Извлекает время начала из интервала в минутах для сортировки."""
    start_time = interval.split('-')[0]
    parts = start_time.split(':')
    return int(parts[0]) * 60 + int(parts[1])


def _merge_consecutive_slots(times: List[str]) -> List[str]:
    """Объединяет последовательные слоты в интервалы."""
    if not times:
        return []
    
    intervals = []
    start_time = times[0]
    prev_time = times[0]
    
    def time_to_minutes(time_str: str) -> int:
        parts = time_str.split(':')
        return int(parts[0]) * 60 + int(parts[1])
    
    for i in range(1, len(times)):
        current_time = times[i]
        current_minutes = time_to_minutes(current_time)
        prev_minutes = time_to_minutes(prev_time)
        
        if current_minutes - prev_minutes == 30:
            prev_time = current_time
        else:
            if start_time == prev_time:
                intervals.append(start_time)
            else:
                intervals.append(f"{start_time}-{prev_time}")
            start_time = current_time
            prev_time = current_time
    
    if start_time == prev_time:
        intervals.append(start_time)
    else:
        intervals.append(f"{start_time}-{prev_time}")
    
    intervals.sort(key=_get_start_time_minutes)
    return intervals


async def find_best_slots(
    yclients_service: YclientsService, 
    service_id: int,
    date: str,
    master_name: Optional[str] = None
) -> Dict[str, any]:
    """
    Находит лучшие доступные слоты для услуги.
    
    Args:
        yclients_service: Экземпляр сервиса Yclients
        service_id: ID услуги
        date: Дата в формате YYYY-MM-DD
        master_name: Имя мастера (опционально)
        
    Returns:
        Dict с service_title, master_name (если указан) и списком интервалов
    """
    # 1. Получаем детали услуги
    service_details = await yclients_service.get_service_details(service_id)
    
    service_name = service_details.name or service_details.title
    if service_name == "Лист ожидания":
        return {
            "service_title": service_name,
            "slots": []
        }
    
    service_title = service_details.get_title()
    
    # Фильтруем мастеров, исключая тех, у которых name == "Лист ожидания"
    all_masters = service_details.staff
    valid_masters = [
        master for master in all_masters 
        if master.name != "Лист ожидания"
    ]
    
    # 2. Если указан master_name, ищем конкретного мастера
    if master_name:
        found_master = _find_master_by_name(valid_masters, master_name)
        
        if not found_master:
            return {
                "service_title": service_title,
                "master_name": master_name,
                "slots": [],
                "error": f"Мастер с именем '{master_name}' не найден для данной услуги"
            }
        
        master_ids = [found_master.id]
        result_master_name = found_master.name
    else:
        master_ids = [master.id for master in valid_masters]
        result_master_name = None
    
    if not master_ids:
        return {
            "service_title": service_title,
            "slots": []
        }
    
    # 3. Параллельно запрашиваем слоты для всех мастеров
    tasks = [
        yclients_service.get_book_times(
            master_id=master_id,
            date=date,
            service_id=service_id
        )
        for master_id in master_ids
    ]
    
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 4. Собираем все временные слоты в один список
    all_times = set()
    for response in responses:
        if isinstance(response, Exception):
            continue
        for slot in response.data:
            all_times.add(slot.time)
    
    # 5. Сортируем временные слоты
    def time_to_minutes(time_str: str) -> int:
        parts = time_str.split(':')
        return int(parts[0]) * 60 + int(parts[1])
    
    sorted_times = sorted(list(all_times), key=time_to_minutes)
    
    # 6. Объединяем слоты в интервалы
    intervals = _merge_consecutive_slots(sorted_times)
    
    result = {
        "service_title": service_title,
        "slots": intervals
    }
    
    if result_master_name:
        result["master_name"] = result_master_name
    
    return result







