"""
Сервис для работы с API Yclients
Адаптирован из Cloud Function для локального использования
"""
import asyncio
import aiohttp
import json
import os
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class Master(BaseModel):
    """Модель мастера из ответа Yclients"""
    id: int
    name: Optional[str] = None


class ServiceDetails(BaseModel):
    """Модель деталей услуги из ответа Yclients"""
    title: str = Field(default="")
    name: str = Field(default="")
    staff: List[Master] = Field(default_factory=list)
    duration: int = Field(default=0, description="Продолжительность услуги в секундах")
    
    def get_title(self) -> str:
        """Возвращает title или name в зависимости от того, что заполнено"""
        return self.title or self.name


class TimeSlot(BaseModel):
    """Модель временного слота"""
    time: str


class BookTimeResponse(BaseModel):
    """Модель ответа с доступными временными слотами"""
    data: List[TimeSlot] = Field(default_factory=list)


class YclientsService:
    """Сервис для работы с API Yclients"""
    
    BASE_URL = "https://api.yclients.com/api/v1"
    
    def __init__(self, auth_header: Optional[str] = None, company_id: Optional[str] = None):
        """
        Инициализация сервиса
        
        Args:
            auth_header: Заголовок авторизации для API (если None, берется из переменных окружения)
            company_id: ID компании в Yclients (если None, берется из переменных окружения)
        """
        # Локально используем AUTH_HEADER и COMPANY_ID из .env
        # В облаке используем AuthenticationToken и CompanyID
        self.auth_header = auth_header or os.getenv('AUTH_HEADER') or os.getenv('AuthenticationToken')
        self.company_id = company_id or os.getenv('COMPANY_ID') or os.getenv('CompanyID')
        
        if not self.auth_header:
            raise ValueError("Не задан AUTH_HEADER или AuthenticationToken в переменных окружения")
        if not self.company_id:
            raise ValueError("Не задан COMPANY_ID или CompanyID в переменных окружения")
    
    async def get_service_details(self, service_id: int) -> ServiceDetails:
        """
        Получить детали услуги
        
        Args:
            service_id: ID услуги
            
        Returns:
            ServiceDetails: Детали услуги
        """
        url = f"https://api.yclients.com/api/v1/company/{self.company_id}/services/{service_id}"
        headers = {
            "Accept": "application/vnd.yclients.v2+json",
            "Authorization": self.auth_header,
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                response_data = await response.json()
                # API возвращает данные в поле 'data'
                service_data = response_data.get('data', response_data)
                return ServiceDetails(**service_data)
    
    async def get_book_times(
        self, 
        master_id: int, 
        date: str, 
        service_id: int
    ) -> BookTimeResponse:
        """
        Получить доступные временные слоты для мастера
        
        Args:
            master_id: ID мастера
            date: Дата в формате YYYY-MM-DD
            service_id: ID услуги
            
        Returns:
            BookTimeResponse: Ответ с доступными временными слотами
        """
        url = f"{self.BASE_URL}/book_times/{self.company_id}/{master_id}/{date}"
        headers = {
            "Accept": "application/vnd.yclients.v2+json",
            "Authorization": self.auth_header,
            "Content-Type": "application/json"
        }
        params = {
            "service_ids": service_id
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                response.raise_for_status()
                response_data = await response.json()
                
                # API может возвращать данные в разных форматах:
                # 1. Массив напрямую: [{...}]
                # 2. Объект с полем 'data': {"success": true, "data": [...]}
                if isinstance(response_data, list):
                    book_data = response_data
                elif isinstance(response_data, dict) and 'data' in response_data:
                    book_data = response_data['data']
                else:
                    book_data = response_data if isinstance(response_data, list) else []
                
                return BookTimeResponse(data=book_data if isinstance(book_data, list) else [])
    
    async def create_booking(
        self,
        staff_id: int,
        service_id: int,
        client_name: str,
        client_phone: str,
        datetime: str,
        seance_length: int
    ) -> Dict[str, Any]:
        """
        Создать запись на услугу
        
        Args:
            staff_id: ID мастера
            service_id: ID услуги
            client_name: Имя клиента
            client_phone: Телефон клиента
            datetime: Дата и время записи
            seance_length: Продолжительность сеанса в секундах
            
        Returns:
            Dict: Ответ от API с информацией о созданной записи
        """
        url = f"{self.BASE_URL}/records/{self.company_id}"
        headers = {
            "Accept": "application/vnd.api.v2+json",
            "Authorization": self.auth_header,
            "Content-Type": "application/json"
        }
        
        body = {
            "staff_id": staff_id,
            "services": [{"id": service_id}],
            "client": {
                "phone": client_phone,
                "name": client_name
            },
            "datetime": datetime,
            "seance_length": seance_length,
            "save_if_busy": False,
            "comment": "ИИ Администратор"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=body) as response:
                response_text = await response.text()
                
                if response.ok:
                    try:
                        data = json.loads(response_text)
                    except json.JSONDecodeError:
                        data = response_text
                    return {"success": True, "data": data}
                else:
                    return {
                        "success": False,
                        "error": response_text[:1000],
                        "status_code": response.status
                    }

