"""
Утилиты для нормализации телефонных номеров
"""
import re


def normalize_phone(phone: str) -> str:
    """
    Нормализует телефонный номер к формату +7XXXXXXXXXX
    
    Примеры:
        "8-922-119-23-69" -> "+79221192369"
        "89221192369" -> "+79221192369"
        "+7 (922) 119-23-69" -> "+79221192369"
        "79221192369" -> "+79221192369"
        "+79221192369" -> "+79221192369"
    
    Args:
        phone: Телефонный номер в любом формате
        
    Returns:
        str: Нормализованный номер в формате +7XXXXXXXXXX
        
    Raises:
        ValueError: Если номер не соответствует ожидаемому формату
    """
    if not phone:
        raise ValueError("Номер телефона не может быть пустым")
    
    # Удаляем все символы кроме цифр и знака +
    cleaned = re.sub(r'[^\d+]', '', phone)
    
    # Удаляем + в начале для унификации
    if cleaned.startswith('+'):
        cleaned = cleaned[1:]
    
    # Приводим к формату 7XXXXXXXXXX
    if cleaned.startswith('8') and len(cleaned) == 11:
        # 89221192369 -> 79221192369
        cleaned = '7' + cleaned[1:]
    elif cleaned.startswith('9') and len(cleaned) == 10:
        # 9221192369 -> 79221192369
        cleaned = '7' + cleaned
    elif cleaned.startswith('7') and len(cleaned) == 11:
        # 79221192369 -> 79221192369
        pass
    else:
        raise ValueError(f"Неверный формат номера телефона: {phone}")
    
    # Проверяем финальную длину
    if len(cleaned) != 11:
        raise ValueError(f"Номер должен содержать 11 цифр, получено: {len(cleaned)}")
    
    # Добавляем + в начало
    return '+' + cleaned

