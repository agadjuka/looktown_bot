"""
Логика для отмены записи клиента
"""
from typing import Dict, Any
from .yclients_service import YclientsService


async def cancel_booking_logic(
    yclients_service: YclientsService,
    record_id: int
) -> Dict[str, Any]:
    """
    Отменить запись по ID
    
    Args:
        yclients_service: Экземпляр YclientsService для работы с API
        record_id: ID записи для отмены
        
    Returns:
        Dict с результатом:
        - success: bool - успешность операции
        - message: str - сообщение о результате
        - error: Optional[str] - сообщение об ошибке
    """
    try:
        # Проверяем валидность record_id
        if not record_id or record_id == 0 or record_id == 1:
            return {
                "success": False,
                "message": None,
                "error": "Неверный ID записи. Сначала узнайте ID записи через инструмент GetClientRecords."
            }
        
        # Отменяем запись
        result = await yclients_service.cancel_record(record_id)
        
        return result
        
    except Exception as e:
        return {
            "success": False,
            "message": None,
            "error": f"Ошибка при отмене записи: {str(e)}"
        }

