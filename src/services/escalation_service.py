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
        # Формируем кликабельную ссылку в формате Markdown
        user_link = f"[{client_telegram_id}](tg://user?id={client_telegram_id})"

        return {
            "user_message": "Секундочку, уточняю ваш вопрос у менеджера.",
            "manager_alert": f"--- MANAGER ALERT ---\nКлиент: {user_link}\n\n{manager_report_text}",
        }


