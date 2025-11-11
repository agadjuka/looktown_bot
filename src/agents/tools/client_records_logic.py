"""
Логика для поиска клиента по телефону и получения его записей
"""
from typing import Dict, Any, Optional
from .yclients_service import YclientsService
from .phone_utils import normalize_phone


async def get_client_records_logic(
    yclients_service: YclientsService,
    phone: str
) -> Dict[str, Any]:
    """
    Найти клиента по телефону и получить все его записи
    
    Args:
        yclients_service: Экземпляр YclientsService для работы с API
        phone: Номер телефона клиента
        
    Returns:
        Dict с результатом:
        - success: bool - успешность операции
        - client: Optional[Dict] - информация о клиенте (id, name, phone)
        - records: List[Dict] - список записей клиента
        - error: Optional[str] - сообщение об ошибке
    """
    try:
        # Нормализуем телефон
        try:
            normalized_phone = normalize_phone(phone)
        except ValueError as e:
            return {
                "success": False,
                "error": f"Неверный формат номера телефона: {str(e)}",
                "client": None,
                "records": []
            }
        
        # Ищем клиента по телефону
        client = await yclients_service.find_client_by_phone(normalized_phone)
        
        if not client:
            return {
                "success": False,
                "error": f"Клиент с номером телефона {phone} не найден в системе",
                "client": None,
                "records": []
            }
        
        # Проверяем валидность ID клиента
        client_id = client.get('id')
        if not client_id or client_id == 0 or client_id == 1:
            return {
                "success": False,
                "error": "Найден клиент, но ID невалиден",
                "client": client,
                "records": []
            }
        
        # Получаем записи клиента
        records = await yclients_service.get_client_records(client_id, count=50)
        
        return {
            "success": True,
            "client": client,
            "records": records,
            "error": None
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Ошибка при получении записей клиента: {str(e)}",
            "client": None,
            "records": []
        }

