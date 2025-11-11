"""
Инструменты для работы с каталогом услуг и бронированием
"""
from .service_tools import (
    GetCategories,
    GetServices,
    BookTimes,
    CreateBooking,
    ViewService
)
from .client_records_tools import GetClientRecords
from .cancel_booking_tools import CancelBooking
from .reschedule_booking_tools import RescheduleBooking
from .call_manager_tools import CallManager
from .about_salon_tools import AboutSalon

__all__ = [
    # Инструменты каталога услуг
    "GetCategories",
    "GetServices",
    "ViewService",
    # Инструменты бронирования
    "BookTimes",
    "CreateBooking",
    # Инструменты для работы с записями клиентов
    "GetClientRecords",
    "CancelBooking",
    "RescheduleBooking",
    # Инструмент передачи менеджеру
    "CallManager",
    # Инструмент информации о салоне
    "AboutSalon",
]


