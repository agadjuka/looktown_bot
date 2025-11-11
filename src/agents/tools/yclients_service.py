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
    category_id: Optional[int] = Field(default=None)
    price_min: Optional[float] = Field(default=None)
    price_max: Optional[float] = Field(default=None)
    active: bool = Field(default=True)
    comment: Optional[str] = Field(default=None)
    
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
    
    async def get_staff_list(self) -> List[Dict[str, Any]]:
        """
        Получить список всех мастеров компании
        
        Returns:
            List[Dict]: Список мастеров с полной информацией
        """
        url = f"{self.BASE_URL}/company/{self.company_id}/staff"
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
                if isinstance(response_data, dict) and 'data' in response_data:
                    return response_data['data']
                elif isinstance(response_data, list):
                    return response_data
                else:
                    return []
    
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
    
    async def find_client_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """
        Найти клиента по номеру телефона
        
        Args:
            phone: Номер телефона клиента
            
        Returns:
            Optional[Dict]: Информация о клиенте (id, name, phone) или None, если не найден
        """
        url = f"{self.BASE_URL}/company/{self.company_id}/clients/search"
        headers = {
            "Accept": "application/vnd.yclients.v2+json",
            "Authorization": self.auth_header,
            "Content-Type": "application/json"
        }
        
        PAGE_SIZE = 200
        MAX_PAGES = 100
        page = 1
        
        # Нормализуем телефон для сравнения (берем последние 10 цифр)
        def extract_digits(s: str) -> str:
            return ''.join(filter(str.isdigit, str(s or '')))
        
        def same_phone(needle: str, hay: str) -> bool:
            n = extract_digits(needle)[-10:]
            h = extract_digits(hay)[-10:]
            return n and h and n == h
        
        async with aiohttp.ClientSession() as session:
            while page <= MAX_PAGES:
                req_body = {
                    "page": page,
                    "page_size": PAGE_SIZE,
                    "fields": ["id", "name", "phone", "email"]
                }
                
                async with session.post(url, headers=headers, json=req_body) as response:
                    if not response.ok:
                        response_text = await response.text()
                        raise aiohttp.ClientResponseError(
                            request_info=response.request_info,
                            history=response.history,
                            status=response.status,
                            message=f"HTTP {response.status}: {response_text[:200]}"
                        )
                    
                    json_data = await response.json()
                    clients_list = json_data.get('data', [])
                    
                    if not isinstance(clients_list, list):
                        clients_list = []
                    
                    # Ищем клиента по телефону
                    for client in clients_list:
                        if same_phone(phone, client.get('phone', '')):
                            return {
                                "id": client.get('id'),
                                "name": client.get('name'),
                                "phone": client.get('phone')
                            }
                    
                    # Проверяем, есть ли еще страницы
                    total = json_data.get('meta', {}).get('total_count', 0)
                    if len(clients_list) < PAGE_SIZE:
                        break
                    if total and page * PAGE_SIZE >= total:
                        break
                    
                    page += 1
        
        return None
    
    async def get_client_records(self, client_id: int, count: int = 50) -> List[Dict[str, Any]]:
        """
        Получить все записи клиента по его ID
        
        Args:
            client_id: ID клиента
            count: Максимальное количество записей для получения (по умолчанию 50)
            
        Returns:
            List[Dict]: Список записей клиента
        """
        url = f"{self.BASE_URL}/records/{self.company_id}"
        headers = {
            "Accept": "application/vnd.yclients.v2+json",
            "Authorization": self.auth_header
        }
        
        params = {
            "client_id": str(client_id),
            "count": str(count)
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                response.raise_for_status()
                response_data = await response.json()
                
                # API возвращает данные в поле 'data'
                records_list = response_data.get('data', [])
                if not isinstance(records_list, list):
                    records_list = []
                
                # Форматируем записи для удобства
                formatted_records = []
                for record in records_list:
                    # Берем первую услугу из массива (если их несколько)
                    service = None
                    if isinstance(record.get('services'), list) and len(record.get('services', [])) > 0:
                        service = record['services'][0]
                    
                    formatted_record = {
                        "record_id": record.get('id'),
                        "client_id": record.get('client', {}).get('id') if isinstance(record.get('client'), dict) else None,
                        "client_name": (
                            record.get('client', {}).get('display_name') or 
                            record.get('client', {}).get('name') if isinstance(record.get('client'), dict) else None
                        ),
                        "service_title": service.get('title') if service else None,
                        "service_id": service.get('id') if service else None,
                        "staff_name": record.get('staff', {}).get('name') if isinstance(record.get('staff'), dict) else None,
                        "staff_id": record.get('staff', {}).get('id') if isinstance(record.get('staff'), dict) else None,
                        "phone": record.get('client', {}).get('phone') if isinstance(record.get('client'), dict) else None,
                        "datetime": record.get('datetime') or record.get('date'),
                        "seance_length": record.get('seance_length') or record.get('length') or None  # Продолжительность в секундах
                    }
                    formatted_records.append(formatted_record)
                
                return formatted_records
    
    async def cancel_record(self, record_id: int) -> Dict[str, Any]:
        """
        Отменить запись по ID
        
        Args:
            record_id: ID записи для отмены
            
        Returns:
            Dict с результатом операции:
            - success: bool - успешность операции
            - message: str - сообщение о результате
            - data: Optional[Dict] - данные об отмененной записи
            - error: Optional[str] - сообщение об ошибке
        """
        url = f"{self.BASE_URL}/record/{self.company_id}/{record_id}"
        headers = {
            "Accept": "application/vnd.yclients.v2+json",
            "Authorization": self.auth_header,
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.delete(url, headers=headers) as response:
                response_text = await response.text()
                
                # Проверяем успешность операции (статус 200-299)
                if 200 <= response.status < 300:
                    return {
                        "success": True,
                        "message": "Запись успешно отменена",
                        "data": {
                            "record_id": record_id,
                            "deleted": True
                        },
                        "error": None
                    }
                else:
                    # Ошибка от API
                    return {
                        "success": False,
                        "message": None,
                        "data": None,
                        "error": f"Ошибка при отмене записи: HTTP {response.status}. {response_text[:500]}"
                    }
    
    async def reschedule_record(
        self,
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
            record_id: ID записи для переноса
            datetime: Новое дата и время в ISO формате (например: "2025-10-29T14:00:00+05:00")
            staff_id: ID мастера
            service_id: ID услуги
            client_id: ID клиента
            seance_length: Продолжительность сеанса в секундах
            save_if_busy: Сохранить запись даже если слот занят (по умолчанию False)
            
        Returns:
            Dict с результатом операции:
            - success: bool - успешность операции
            - message: str - сообщение о результате
            - data: Optional[Dict] - данные об обновленной записи
            - error: Optional[str] - сообщение об ошибке
        """
        url = f"{self.BASE_URL}/record/{self.company_id}/{record_id}"
        headers = {
            "Accept": "application/vnd.yclients.v2+json",
            "Authorization": self.auth_header,
            "Content-Type": "application/json"
        }
        
        body = {
            "staff_id": staff_id,
            "services": [{"id": service_id}],
            "client": {"id": client_id},
            "seance_length": seance_length,
            "datetime": datetime,
            "save_if_busy": 1 if save_if_busy else 0
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.put(url, headers=headers, json=body) as response:
                response_text = await response.text()
                
                # Проверяем успешность операции (статус 200-299)
                if 200 <= response.status < 300:
                    return {
                        "success": True,
                        "message": "Запись успешно перенесена",
                        "data": {
                            "record_id": record_id,
                            "updated": {
                                "datetime": datetime,
                                "staff_id": staff_id,
                                "service_id": service_id,
                                "seance_length": seance_length
                            }
                        },
                        "error": None
                    }
                else:
                    # Обработка типовых ошибок
                    if response.status == 409:
                        return {
                            "success": False,
                            "message": None,
                            "data": None,
                            "error": "Слот занят или нерабочее время. Выберите другое время."
                        }
                    elif response.status == 422:
                        return {
                            "success": False,
                            "message": None,
                            "data": None,
                            "error": "Ошибка валидации данных. Проверьте правильность всех параметров."
                        }
                    else:
                        return {
                            "success": False,
                            "message": None,
                            "data": None,
                            "error": f"Ошибка при переносе записи: HTTP {response.status}. {response_text[:500]}"
                        }
