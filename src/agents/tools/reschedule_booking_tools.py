"""
Инструмент для переноса записи клиента
"""
import asyncio
from typing import Optional
from pydantic import BaseModel, Field
from yandex_cloud_ml_sdk._threads.thread import Thread

from .yclients_service import YclientsService
from .reschedule_booking_logic import reschedule_booking_logic

try:
    from ..services.logger_service import logger
except ImportError:
    # Простой logger для случаев, когда logger_service недоступен
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class RescheduleBooking(BaseModel):
    """
    Перенести запись клиента на новое время.
    Используй когда клиент просит перенести запись на другое время или дату.
    record_id, staff_id, service_id, client_id и seance_length получай из GetClientRecords - каждая запись содержит эти данные.
    datetime в формате YYYY-MM-DD HH:MM (например "2025-11-12 14:30") или YYYY-MM-DDTHH:MM.
    """
    
    record_id: int = Field(
        description="ID записи для переноса (число). Получи из GetClientRecords - каждая запись имеет ID записи."
    )
    
    datetime: str = Field(
        description="Новое дата и время в формате YYYY-MM-DD HH:MM (например '2025-11-12 14:30') или YYYY-MM-DDTHH:MM"
    )
    
    staff_id: int = Field(
        description="ID мастера (число). Получи из GetClientRecords - каждая запись содержит staff_id."
    )
    
    service_id: int = Field(
        description="ID услуги (число). Получи из GetClientRecords - каждая запись содержит service_id."
    )
    
    client_id: int = Field(
        description="ID клиента (число). Получи из GetClientRecords - каждая запись содержит client_id."
    )
    
    seance_length: int = Field(
        description="Продолжительность сеанса в секундах (число). Получи из GetClientRecords или из услуги."
    )
    
    save_if_busy: Optional[bool] = Field(
        default=False,
        description="Сохранить запись даже если слот занят (по умолчанию False). Обычно не используй."
    )
    
    def process(self, thread: Thread) -> str:
        """
        Перенос записи на новое время
        
        Returns:
            Сообщение о результате переноса записи
        """
        try:
            # Создаем сервис (он сам возьмет переменные окружения)
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
            # Запускаем async функцию синхронно
            result = asyncio.run(
                reschedule_booking_logic(
                    yclients_service=yclients_service,
                    record_id=self.record_id,
                    datetime=self.datetime,
                    staff_id=self.staff_id,
                    service_id=self.service_id,
                    client_id=self.client_id,
                    seance_length=self.seance_length,
                    save_if_busy=self.save_if_busy
                )
            )
            
            # Проверяем результат
            if result.get('success'):
                # Возвращаем мягкое сообщение об успешном переносе
                return result.get('message', 'Запись успешно перенесена')
            else:
                error = result.get('error', 'Неизвестная ошибка')
                return f"Ошибка: {error}"
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации RescheduleBooking: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при переносе записи: {e}", exc_info=True)
            return f"Ошибка при переносе записи: {str(e)}"















