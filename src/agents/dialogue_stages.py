"""
Определение стадий диалога
Соответствует стадиям из dialogue_patterns.json
"""
from enum import Enum


class DialogueStage(str, Enum):
    """Стадии диалога"""
    GREETING = "greeting"                      # Приветствие, начало диалога
    INFORMATION_GATHERING = "information_gathering"  # Сбор информации об услугах, ценах, мастерах
    BOOKING = "booking"                        # Бронирование услуги
    BOOKING_TO_MASTER = "booking_to_master"   # Бронирование к конкретному мастеру
    CANCELLATION_REQUEST = "cancellation_request"  # Запрос на отмену записи
    RESCHEDULE = "reschedule"                 # Перенос записи
    VIEW_MY_BOOKING = "view_my_booking"        # Просмотр своих записей