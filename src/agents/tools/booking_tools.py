"""
Инструменты для работы с системой бронирования
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from yandex_cloud_ml_sdk._threads.thread import Thread


class CheckAvailableSlots(BaseModel):
    """Проверка доступных слотов"""
    date: str = Field(description="Дата в формате YYYY-MM-DD")
    service_type: Optional[str] = Field(description="Тип услуги", default=None)
    
    def process(self, thread: Thread) -> str:
        """
        Проверка доступных слотов на указанную дату
        
        Args:
            thread: Thread для доступа к контексту диалога
            
        Returns:
            Строка с информацией о доступных слотах
        """
        # TODO: Реализовать обращение к API системы бронирования
        # Пока заглушка
        if self.service_type:
            return f"Доступные слоты на {self.date} для услуги '{self.service_type}': 10:00, 11:00, 14:00, 16:00"
        return f"Доступные слоты на {self.date}: 10:00, 11:00, 14:00, 16:00"


class CreateBooking(BaseModel):
    """Создание бронирования"""
    date: str = Field(description="Дата в формате YYYY-MM-DD")
    time: str = Field(description="Время в формате HH:MM")
    service_type: str = Field(description="Тип услуги")
    client_name: Optional[str] = Field(description="Имя клиента", default=None)
    client_phone: Optional[str] = Field(description="Телефон клиента", default=None)
    
    def process(self, thread: Thread) -> str:
        """
        Создание нового бронирования
        
        Args:
            thread: Thread для доступа к контексту диалога
            
        Returns:
            Строка с информацией о созданном бронировании
        """
        # TODO: Реализовать создание бронирования через API
        # Пока заглушка
        booking_id = f"BK-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        client_info = ""
        if self.client_name:
            client_info += f" Имя: {self.client_name}."
        if self.client_phone:
            client_info += f" Телефон: {self.client_phone}."
        
        return (
            f"Бронирование создано! ID: {booking_id}. "
            f"Дата: {self.date}, время: {self.time}, услуга: {self.service_type}.{client_info}"
        )


class GetBooking(BaseModel):
    """Получение информации о бронировании"""
    booking_id: Optional[str] = Field(description="ID бронирования", default=None)
    phone: Optional[str] = Field(description="Телефон клиента", default=None)
    
    def process(self, thread: Thread) -> str:
        """
        Получение информации о существующем бронировании
        
        Args:
            thread: Thread для доступа к контексту диалога
            
        Returns:
            Строка с информацией о бронировании
        """
        # TODO: Реализовать получение бронирования через API
        # Пока заглушка
        if self.booking_id:
            return (
                f"Информация о бронировании {self.booking_id}: "
                f"Дата: 2024-12-20, время: 15:00, услуга: Стрижка, статус: Подтверждено"
            )
        elif self.phone:
            return (
                f"Найдено бронирование по телефону {self.phone}: "
                f"ID: BK-20241220150000, Дата: 2024-12-20, время: 15:00, услуга: Стрижка"
            )
        else:
            return "Не указан ID бронирования или телефон для поиска"


class CancelBooking(BaseModel):
    """Отмена бронирования"""
    booking_id: str = Field(description="ID бронирования")
    reason: Optional[str] = Field(description="Причина отмены", default=None)
    
    def process(self, thread: Thread) -> str:
        """
        Отмена существующего бронирования
        
        Args:
            thread: Thread для доступа к контексту диалога
            
        Returns:
            Строка с подтверждением отмены
        """
        # TODO: Реализовать отмену бронирования через API
        # Пока заглушка
        reason_text = f" Причина: {self.reason}." if self.reason else ""
        return f"Бронирование {self.booking_id} успешно отменено.{reason_text}"


class RescheduleBooking(BaseModel):
    """Перенос бронирования"""
    booking_id: str = Field(description="ID бронирования")
    new_date: str = Field(description="Новая дата в формате YYYY-MM-DD")
    new_time: str = Field(description="Новое время в формате HH:MM")
    
    def process(self, thread: Thread) -> str:
        """
        Перенос существующего бронирования на новую дату и время
        
        Args:
            thread: Thread для доступа к контексту диалога
            
        Returns:
            Строка с подтверждением переноса
        """
        # TODO: Реализовать перенос бронирования через API
        # Пока заглушка
        return (
            f"Бронирование {self.booking_id} успешно перенесено на {self.new_date} {self.new_time}"
        )

