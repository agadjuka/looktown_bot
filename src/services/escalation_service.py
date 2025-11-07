"""
Сервис обработки эскалации диалога на менеджера.
"""

from typing import Dict


class EscalationService:
    """Отвечает только за обработку сигнала эскалации [CALL_MANAGER]."""

    def handle(self, llm_response_text: str, client_telegram_id: str) -> Dict[str, str]:
        """
        Обработать сигнал эскалации и сформировать раздельные сообщения.

        :param llm_response_text: Полный текст ответа LLM, начинающийся с [CALL_MANAGER]
        :param client_telegram_id: Идентификатор клиента в Telegram
        :return: Словарь с сообщением для пользователя и алертом для менеджера
        """
        text = llm_response_text or ""
        prefix = "[CALL_MANAGER]"
        manager_report_text = text[text.find(prefix) + len(prefix):].lstrip()
        
        # Переворачиваем порядок истории сообщений (старое сверху, новое снизу)
        manager_report_text = self._reverse_message_history(manager_report_text)
        
        # Формируем кликабельную ссылку в формате Markdown
        user_link = f"[{client_telegram_id}](tg://user?id={client_telegram_id})"

        return {
            "user_message": "Секундочку, уточняю ваш вопрос у менеджера.",
            "manager_alert": f"--- MANAGER ALERT ---\nКлиент: {user_link}\n\n{manager_report_text}",
        }
    
    def _reverse_message_history(self, text: str) -> str:
        """
        Переворачивает порядок истории сообщений.
        Разбивает текст на блоки по двойным переносам строк и переворачивает их порядок.
        
        :param text: Текст с историей сообщений (новое сверху, старое снизу)
        :return: Текст с историей сообщений (старое сверху, новое снизу)
        """
        if not text:
            return text
        
        # Разбиваем на блоки по двойным переносам строк (пустые строки между сообщениями)
        blocks = text.split('\n\n')
        
        # Если блоков больше одного, переворачиваем порядок
        if len(blocks) > 1:
            blocks = blocks[::-1]
            return '\n\n'.join(blocks)
        
        # Если блок один, пытаемся разбить по одинарным переносам
        lines = text.split('\n')
        if len(lines) > 1:
            # Проверяем, есть ли паттерн истории сообщений (например, строки с временными метками или отступами)
            # Если да, переворачиваем
            lines = lines[::-1]
            return '\n'.join(lines)
        
        # Если ничего не подошло, возвращаем как есть
        return text

    def handle_api_error(self, error_message: str, client_telegram_id: str, user_message: str) -> Dict[str, str]:
        """
        Обработать ошибку API и сформировать менеджер-алерт.

        :param error_message: Текст ошибки API
        :param client_telegram_id: Идентификатор клиента в Telegram
        :param user_message: Исходное сообщение пользователя
        :return: Словарь с сообщением для пользователя и алертом для менеджера
        """
        # Формируем кликабельную ссылку в формате Markdown
        user_link = f"[{client_telegram_id}](tg://user?id={client_telegram_id})"

        return {
            "user_message": "Секундочку, уточняю у менеджера на ваш вопрос.",
            "manager_alert": f"--- MANAGER ALERT ---\nКлиент: {user_link}\n\nОтчет от менеджера: Ошибка API: {error_message}",
        }


