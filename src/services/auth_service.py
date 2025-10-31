"""
Сервис для аутентификации с Yandex Cloud API
"""
import os
import time
import json
import jwt
import requests
from typing import Optional


class AuthService:
    """Сервис для работы с аутентификацией Yandex Cloud"""
    
    def __init__(self):
        """Инициализация сервиса аутентификации"""
        self.api_key = os.getenv("YANDEX_API_KEY_SECRET")
        self.service_account_id = None
        self.service_account_key_id = None
        self.service_account_private_key = None
        
        if not self.api_key:
            raise ValueError("Не задан YANDEX_API_KEY_SECRET в переменных окружения")
        
        # Загружаем данные сервисного аккаунта
        self._load_service_account_data()
    
    def _load_service_account_data(self):
        """Загрузить данные сервисного аккаунта из файла."""
        try:
            key_file_path = os.getenv("YANDEX_SERVICE_ACCOUNT_KEY_FILE", "key.json")
            with open(key_file_path, 'r', encoding='utf-8') as f:
                key_data = json.load(f)
            
            self.service_account_id = key_data['service_account_id']
            self.service_account_key_id = key_data['id']
            self.service_account_private_key = key_data['private_key']
            
            print(f"Загружен сервисный аккаунт: {self.service_account_id}")
            
        except Exception as e:
            print(f"Не удалось загрузить сервисный аккаунт: {e}")
            # Fallback к API ключу
            self.service_account_id = None
            self.service_account_key_id = None
            self.service_account_private_key = None
    
    def _create_jwt_token(self) -> str:
        """Создать JWT токен для аутентификации с сервисным аккаунтом."""
        if not self.service_account_private_key:
            raise ValueError("Сервисный аккаунт не настроен")
            
        now = int(time.time())
        payload = {
            'aud': 'https://iam.api.cloud.yandex.net/iam/v1/tokens',
            'iss': self.service_account_id,
            'iat': now,
            'exp': now + 3600  # Токен действителен 1 час
        }
        
        token = jwt.encode(
            payload,
            self.service_account_private_key,
            algorithm='PS256',
            headers={'kid': self.service_account_key_id}
        )
        return token
    
    def _get_iam_token(self) -> str:
        """Получить IAM токен для аутентификации."""
        jwt_token = self._create_jwt_token()
        
        url = "https://iam.api.cloud.yandex.net/iam/v1/tokens"
        headers = {"Content-Type": "application/json"}
        data = {"jwt": jwt_token}
        
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        return result["iamToken"]
    
    def get_iam_token(self) -> str:
        """Публичный метод для получения IAM токена"""
        return self._get_iam_token()
    
    def get_api_key(self) -> str:
        """Получить API ключ"""
        return self.api_key
    
    def is_service_account_configured(self) -> bool:
        """Проверить, настроен ли сервисный аккаунт"""
        return self.service_account_id is not None
