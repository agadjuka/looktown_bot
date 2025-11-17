"""
Инструменты для работы с каталогом услуг и бронированием
"""
from .service_tools import (
    GetCategories,
    GetServices,
    FindSlots,
    CreateBooking,
    ViewService,
    FindMasterByService
)
from .client_records_tools import GetClientRecords
from .cancel_booking_tools import CancelBooking
from .reschedule_booking_tools import RescheduleBooking
from .call_manager_tools import CallManager
from .about_salon_tools import AboutSalon
from .masters_tools import Masters

__all__ = [
    # Инструменты каталога услуг
    "GetCategories",
    "GetServices",
    "ViewService",
    # Инструменты бронирования
    "FindSlots",
    "CreateBooking",
    "FindMasterByService",
    # Инструменты для работы с записями клиентов
    "GetClientRecords",
    "CancelBooking",
    "RescheduleBooking",
    # Инструмент передачи менеджеру
    "CallManager",
    # Инструмент информации о салоне
    "AboutSalon",
    # Инструмент информации о мастерах
    "Masters",
]


