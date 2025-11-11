"""
Инструмент для передачи диалога менеджеру
"""
from typing import Optional
from pydantic import BaseModel, Field
from yandex_cloud_ml_sdk._threads.thread import Thread

try:
    from ..services.logger_service import logger
except ImportError:
    class SimpleLogger:
        def error(self, msg, *args, **kwargs):
            print(f"ERROR: {msg}")
    logger = SimpleLogger()


class CallManagerException(Exception):
    """Специальное исключение для прекращения работы агента после вызова CallManager"""
    def __init__(self, escalation_result: dict):
        self.escalation_result = escalation_result
        super().__init__("CallManager вызван")


class CallManager(BaseModel):
    """
    Передать диалог менеджеру.
    Используй этот инструмент в трех случаях:
    1. Если клиент выражает сильное недовольство, жалуется, требует возврата денег
    2. Если запрос клиента очень нестандартный и требует принятия бизнес-решения (например, обсуждение сотрудничества, особых скидок)
    3. Если ты сталкиваешься с технической ошибкой при вызове других инструментов
    
    После вызова этого инструмента твоя работа завершается - не давай никакого ответа клиенту.
    """
    
    reason: str = Field(
        description="Краткое описание причины вызова менеджера. Например: 'Клиент жалуется на качество услуги', 'Клиент задал вопрос на который я не знаю ответа', 'Произошла ошибка при использовании инструмента BookTimes'"
    )
    
    def process(self, thread: Thread) -> str:
        """
        Обработка вызова CallManager
        
        Args:
            thread: Thread с историей диалога
            
        Returns:
            Строка с маркером [CALL_MANAGER] для обработки в BaseAgent
        """
        try:
            from ..services.escalation_service import EscalationService
            from ..services.logger_service import logger
            
            # Извлекаем последние сообщения из Thread
            messages = self._extract_last_messages(thread, count=3)
            
            # Формируем отчет для менеджера
            manager_report = self._format_manager_report(self.reason, messages)
            
            # Получаем chat_id из thread (если сохранен) или используем thread_id
            chat_id = getattr(thread, 'chat_id', None)
            if not chat_id:
                # Пробуем получить из thread.id
                chat_id = getattr(thread, 'id', 'unknown')
            
            # Создаем EscalationService и обрабатываем
            escalation_service = EscalationService()
            
            # Формируем текст в формате [CALL_MANAGER] для EscalationService
            call_manager_text = f"[CALL_MANAGER]\n{manager_report}"
            
            # Обрабатываем через EscalationService
            escalation_result = escalation_service.handle(call_manager_text, str(chat_id))
            
            # Выбрасываем специальное исключение для прекращения работы агента
            raise CallManagerException(escalation_result)
            
        except CallManagerException:
            # Пробрасываем исключение дальше
            raise
        except Exception as e:
            logger.error(f"Ошибка при вызове CallManager: {e}")
            # Если ошибка, все равно выбрасываем CallManagerException с базовым сообщением
            escalation_service = EscalationService()
            chat_id = getattr(thread, 'chat_id', None) or getattr(thread, 'id', 'unknown')
            fallback_text = f"[CALL_MANAGER]\nОтчет для менеджера:\nПричина: {self.reason}\nОшибка при извлечении истории: {str(e)}"
            escalation_result = escalation_service.handle(fallback_text, str(chat_id))
            raise CallManagerException(escalation_result)
    
    def _extract_last_messages(self, thread: Thread, count: int = 3) -> list:
        """
        Извлекает последние N сообщений из Thread
        
        Args:
            thread: Thread с историей диалога
            count: Количество последних сообщений для извлечения
            
        Returns:
            Список сообщений в формате [{"role": "user"|"assistant", "content": "..."}]
        """
        messages = []
        try:
            # Получаем все сообщения из thread
            thread_messages = list(thread) if hasattr(thread, '__iter__') else []
            
            # Берем последние count сообщений
            last_messages = thread_messages[-count:] if len(thread_messages) > count else thread_messages
            
            for msg in last_messages:
                # Определяем роль сообщения
                role = "user"
                content = ""
                
                # Проверяем атрибуты сообщения
                if hasattr(msg, 'role'):
                    role = msg.role
                elif hasattr(msg, 'author_role'):
                    role = msg.author_role
                
                # Получаем содержимое
                if hasattr(msg, 'content'):
                    content = msg.content
                elif hasattr(msg, 'text'):
                    content = msg.text
                elif hasattr(msg, 'parts'):
                    # Если есть parts, берем текст из первого part
                    parts = msg.parts
                    if parts and len(parts) > 0:
                        first_part = parts[0]
                        if hasattr(first_part, 'text'):
                            content = first_part.text
                        elif isinstance(first_part, dict) and 'text' in first_part:
                            content = first_part['text']
                
                # Нормализуем роль
                if role in ['user', 'USER', 'User']:
                    role = "user"
                elif role in ['assistant', 'ASSISTANT', 'Assistant', 'model', 'MODEL']:
                    role = "assistant"
                else:
                    # По умолчанию считаем user
                    role = "user"
                
                if content:
                    messages.append({
                        "role": role,
                        "content": str(content)
                    })
        
        except Exception as e:
            logger.error(f"Ошибка при извлечении сообщений из Thread: {e}")
            # Возвращаем пустой список или базовое сообщение
            messages = [{"role": "user", "content": "Не удалось извлечь историю сообщений"}]
        
        return messages
    
    def _format_manager_report(self, reason: str, messages: list) -> str:
        """
        Форматирует отчет для менеджера
        
        Args:
            reason: Причина вызова менеджера
            messages: Список последних сообщений
            
        Returns:
            Отформатированный текст отчета
        """
        report_lines = [
            "Отчет для менеджера:",
            f"Причина: {reason}",
            ""
        ]
        
        if messages:
            report_lines.append("История последних сообщений:")
            for msg in messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                role_label = "user" if role == "user" else "assistant"
                report_lines.append(f"- {role_label}: {content}")
        else:
            report_lines.append("История сообщений недоступна")
        
        return "\n".join(report_lines)

