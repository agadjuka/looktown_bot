"""
Логика для переноса записи клиента
"""
from typing import Dict, Any
from .yclients_service import YclientsService


async def reschedule_booking_logic(
    yclients_service: YclientsService,
    record_id: int,
    datetime: str,
    staff_id: int,
    service_id: int,
    client_id: int,
    seance_length: int,
    save_if_busy: bool = False
) -> Dict[str, Any]:
    """
    Перенести запись на новое время
    
    Args:
        yclients_service: Экземпляр YclientsService для работы с API
        record_id: ID записи для переноса
        datetime: Новое дата и время в ISO формате
        staff_id: ID мастера
        service_id: ID услуги
        client_id: ID клиента
        seance_length: Продолжительность сеанса в секундах
        save_if_busy: Сохранить запись даже если слот занят
        
    Returns:
        Dict с результатом:
        - success: bool - успешность операции
        - message: str - сообщение о результате
        - error: Optional[str] - сообщение об ошибке
    """
    try:
        # Валидация параметров
        if not record_id or record_id == 0 or record_id == 1:
            return {
                "success": False,
                "message": None,
                "error": "Неверный ID записи. Сначала узнайте ID записи через инструмент GetClientRecords."
            }
        
        if not datetime or datetime == "1":
            return {
                "success": False,
                "message": None,
                "error": "Не указана дата и время. Укажите дату и время в формате YYYY-MM-DD HH:MM или YYYY-MM-DDTHH:MM."
            }
        
        if not staff_id or staff_id == 0 or staff_id == 1:
            return {
                "success": False,
                "message": None,
                "error": "Неверный ID мастера. Сначала получите мастера через инструмент FindMasterByService или FindSlots."
            }
        
        if not service_id or service_id == 0 or service_id == 1:
            return {
                "success": False,
                "message": None,
                "error": "Неверный ID услуги. Сначала получите услуги через инструмент GetServices."
            }
        
        if not client_id or client_id == 0 or client_id == 1:
            return {
                "success": False,
                "message": None,
                "error": "Неверный ID клиента. Сначала узнайте ID клиента через инструмент GetClientRecords."
            }
        
        if not seance_length or seance_length <= 0:
            return {
                "success": False,
                "message": None,
                "error": "Не указана длительность сеанса в секундах. Возьмите из услуги или записи."
            }
        
        # Переносим запись
        result = await yclients_service.reschedule_record(
            record_id=record_id,
            datetime=datetime,
            staff_id=staff_id,
            service_id=service_id,
            client_id=client_id,
            seance_length=seance_length,
            save_if_busy=save_if_busy
        )
        
        return result
        
    except Exception as e:
        return {
            "success": False,
            "message": None,
            "error": f"Ошибка при переносе записи: {str(e)}"
        }















