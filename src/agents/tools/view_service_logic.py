"""
Логика для получения деталей услуги
Адаптировано из Cloud Function viewService
"""
import aiohttp
from typing import Dict, Any
from .yclients_service import YclientsService


async def view_service_logic(
    yclients_service: YclientsService,
    service_id: int
) -> Dict[str, Any]:
    """
    Получает детали услуги по ID
    
    Args:
        yclients_service: Экземпляр сервиса Yclients
        service_id: ID услуги
        
    Returns:
        Dict с деталями услуги или ошибкой
    """
    try:
        # Проверяем валидность service_id
        if not service_id or service_id == 1:
            return {
                "success": False,
                "error": "bad_service_id",
                "message": "Сначала получи ID услуги через GetServices"
            }
        
        # Получаем детали услуги
        service_details = await yclients_service.get_service_details(service_id)
        
        # Фильтруем мастеров, исключая "Лист ожидания"
        filtered_staff = []
        if service_details.staff:
            for master in service_details.staff:
                if master.name and master.name.lower() != "лист ожидания":
                    filtered_staff.append({
                        "id": master.id,
                        "name": master.name
                    })
        
        # Формируем результат
        service_data = {
            "id": service_id,
            "title": service_details.get_title(),
            "category_id": service_details.category_id,
            "duration_sec": service_details.duration,
            "price_min": service_details.price_min,
            "price_max": service_details.price_max,
            "active": service_details.active,
            "comment": service_details.comment,
            "comment_plain": None,
            "staff": filtered_staff
        }
        
        # Формируем comment_plain (упрощенный комментарий без лишних пробелов)
        if service_data["comment"]:
            comment_plain = " ".join(service_data["comment"].split())
            service_data["comment_plain"] = comment_plain
        
        return {
            "success": True,
            "service": service_data
        }
        
    except aiohttp.ClientResponseError as e:
        return {
            "success": False,
            "error": "yclients_http_error",
            "status": e.status,
            "message": f"Ошибка HTTP {e.status}: {e.message}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": "internal_error",
            "message": str(e)
        }

