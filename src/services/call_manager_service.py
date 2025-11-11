"""
Сервис для вызова CallManager при критических ошибках
"""
from ..services.logger_service import logger


class CallManagerService:
    """Сервис для обработки критических ошибок через CallManager"""
    
    @staticmethod
    def handle_critical_error(
        error_message: str,
        agent_name: str,
        message: str,
        thread_id: str = None
    ) -> None:
        """
        Заглушка для вызова CallManager при критических ошибках
        
        :param error_message: Сообщение об ошибке
        :param agent_name: Имя агента, в котором произошла ошибка
        :param message: Исходное сообщение пользователя
        :param thread_id: ID потока (опционально)
        """
        logger.error(f"CallManager вызван для агента {agent_name}")
        logger.error(f"Ошибка: {error_message}")
        logger.error(f"Исходное сообщение: {message[:200]}")
        if thread_id:
            logger.error(f"Thread ID: {thread_id}")
        
        # TODO: Здесь будет реализована логика вызова CallManager
        # Пока это заглушка
        logger.warning("CallManager: Заглушка - реальная логика будет добавлена позже")





