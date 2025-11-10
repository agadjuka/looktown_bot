"""
Состояние для графа бронирования
"""
from typing import TypedDict, Optional
from yandex_cloud_ml_sdk._threads.thread import Thread


class BookingState(TypedDict):
    """Состояние графа бронирования"""
    message: str                    # Исходное сообщение пользователя
    thread: Thread                  # Thread для всех агентов (общая история)
    stage: Optional[str]            # Определённая стадия диалога
    extracted_info: Optional[dict]  # Извлечённая информация
    answer: str                     # Финальный ответ пользователю
    manager_alert: Optional[str]    # Сообщение для менеджера (если нужно)

