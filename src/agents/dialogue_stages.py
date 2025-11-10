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
    GENERAL = "general"                # Общий вопрос
    UNKNOWN = "unknown"                 # Неопределённая стадия

