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












