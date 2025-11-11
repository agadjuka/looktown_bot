"""
Сервис для проверки типов ошибок
"""
from typing import Optional


class ErrorChecker:
    """Класс для проверки различных типов ошибок"""
    
    @staticmethod
    def is_internal_server_error(error_message: Optional[str]) -> bool:
        """
        Проверяет, является ли ошибка InternalServerError (500)
        
        :param error_message: Текст ошибки или сообщение об ошибке
        :return: True, если это InternalServerError
        """
        if not error_message:
            return False
        
        error_lower = str(error_message).lower()
        return (
            "500: internal server error" in error_lower or
            "internal server error" in error_lower or
            "500" in error_lower and "internal" in error_lower
        )





