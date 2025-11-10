"""
Определение стадий диалога
"""
from enum import Enum


class DialogueStage(str, Enum):
    """Стадии диалога"""
    GREETING = "greeting"              # Приветствие
    BOOKING = "booking"                # Бронирование
    CANCEL_BOOKING = "cancel_booking"  # Отмена записи
    RESCHEDULE = "reschedule"           # Перенос записи
    SALON_INFO = "salon_info"          # О салоне
    GENERAL = "general"                # Общий вопрос
    UNKNOWN = "unknown"                # Неопределённая стадия
