"""
Инструмент для отмены записи клиента
"""
import asyncio
from pydantic import BaseModel, Field
from yandex_cloud_ml_sdk._threads.thread import Thread

from .yclients_service import YclientsService
from .cancel_booking_logic import cancel_booking_logic

try:
    from ..services.logger_service import logger
except ImportError:
    # Простой logger для случаев, когда logger_service недоступен
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class CancelBooking(BaseModel):
    """
    Отменить запись клиента по ID записи.
    Используй когда клиент просит отменить запись или перенести её.
    record_id получай из GetClientRecords - каждая запись имеет ID записи.
    """
    
    record_id: int = Field(
        description="ID записи для отмены (число). Получи из GetClientRecords - каждая запись имеет ID записи."
    )
    
    def process(self, thread: Thread) -> str:
        """
        Отмена записи по ID
        
        Returns:
            Сообщение о результате отмены записи
        """
        try:
            # Создаем сервис (он сам возьмет переменные окружения)
            try:
                yclients_service = YclientsService()
            except ValueError as e:
                return f"Ошибка конфигурации: {str(e)}. Проверьте переменные окружения AUTH_HEADER/AuthenticationToken и COMPANY_ID/CompanyID."
            
            # Запускаем async функцию синхронно
            result = asyncio.run(
                cancel_booking_logic(
                    yclients_service=yclients_service,
                    record_id=self.record_id
                )
            )
            
            # Проверяем результат
            if result.get('success'):
                # Возвращаем мягкое сообщение об успешной отмене
                return result.get('message', 'Запись успешно отменена')
            else:
                error = result.get('error', 'Неизвестная ошибка')
                return f"Ошибка: {error}"
            
        except ValueError as e:
            logger.error(f"Ошибка конфигурации CancelBooking: {e}")
            return f"Ошибка конфигурации: {str(e)}"
        except Exception as e:
            logger.error(f"Ошибка при отмене записи: {e}", exc_info=True)
            return f"Ошибка при отмене записи: {str(e)}"

