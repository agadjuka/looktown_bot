import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from service_factory import get_yandex_agent_service
from src.services.logger_service import logger
from src.services.date_normalizer import normalize_dates_in_text
from src.services.time_normalizer import normalize_times_in_text
from src.services.retry_service import RetryService
from src.services.call_manager_service import CallManagerException
from src.services.escalation_service import EscalationService

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

async def send_to_agent(message_text, chat_id):
    """Отправка сообщения агенту через LangGraph с retry на нижнем уровне"""
    async def _execute_agent_request():
        """Внутренняя функция для выполнения запроса к агенту"""
        logger.agent("Обработка сообщения", chat_id)
        yandex_agent_service = get_yandex_agent_service()
        response = await yandex_agent_service.send_to_agent(chat_id, message_text)
        logger.agent("Ответ получен", chat_id)
        return response
    
    try:
        # Используем RetryService для retry на нижнем уровне (async версия)
        response = await RetryService.execute_with_retry_async(
            operation=_execute_agent_request,
            max_retries=3,
            operation_name="отправка сообщения агенту",
            context_info={
                "chat_id": chat_id,
                "message": message_text
            }
        )
        return response
    except CallManagerException as e:
        # Обрабатываем вызов CallManager - возвращаем результат эскалации
        logger.info("CallManager был вызван из-за критической ошибки")
        return e.escalation_result
    except Exception as e:
        logger.error("Ошибка при обращении к агенту", str(e))
        return {"user_message": f"Ошибка при обращении к агенту: {str(e)}"}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    chat_id = str(update.effective_chat.id)
    logger.telegram("Команда /start", chat_id)
    await update.message.reply_text('Добрый день!\nНа связи менеджер LOOKTOWN 🌻\n\nЧем я могу вам помочь?')

async def new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /new - сброс контекста"""
    chat_id = str(update.effective_chat.id)
    logger.telegram("Команда /new", chat_id)
    try:
        yandex_agent_service = get_yandex_agent_service()
        await yandex_agent_service.reset_context(chat_id)
        logger.success("Контекст сброшен", chat_id)
        await update.message.reply_text('Контекст сброшен. Начинаем новый диалог!')
    except Exception as e:
        logger.error("Ошибка при сбросе контекста", str(e))
        await update.message.reply_text(f'Ошибка при сбросе контекста: {str(e)}')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_message = update.message.text
    chat_id = str(update.effective_chat.id)
    
    logger.telegram("Получено сообщение", chat_id)
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    agent_response = await send_to_agent(user_message, chat_id)
    # Ожидаем словарь: {"user_message": str, "manager_alert": Optional[str]}
    user_message_text = agent_response.get("user_message") if isinstance(agent_response, dict) else str(agent_response)
    
    # Проверяем на эскалацию [CALL_MANAGER] перед отправкой в Telegram
    if user_message_text and user_message_text.strip().startswith('[CALL_MANAGER]'):
        escalation_service = EscalationService()
        escalation_result = escalation_service.handle(user_message_text, chat_id)
        user_message_text = escalation_result.get("user_message", user_message_text)
        # Обновляем agent_response с результатом эскалации
        agent_response = {
            "user_message": user_message_text,
            "manager_alert": escalation_result.get("manager_alert")
        }
    
    # Нормализуем даты и время в ответе
    user_message_text = normalize_dates_in_text(user_message_text)
    user_message_text = normalize_times_in_text(user_message_text)
    await update.message.reply_text(user_message_text, parse_mode=ParseMode.MARKDOWN)

    # Временная заглушка: отправляем alert менеджера тем же пользователю вторым сообщением
    if isinstance(agent_response, dict) and agent_response.get("manager_alert"):
        manager_alert = normalize_dates_in_text(agent_response["manager_alert"])
        manager_alert = normalize_times_in_text(manager_alert)
        try:
            await update.message.reply_text(manager_alert, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.warning(f"Ошибка при отправке manager_alert с Markdown: {e}, отправляю без форматирования")
            # Отправляем без Markdown в случае ошибки парсинга
            await update.message.reply_text(manager_alert, parse_mode=None)
    logger.telegram("Ответ отправлен", chat_id)

def main():
    """Основная функция запуска бота"""
    logger.info("🚀 Запуск бота с LangGraph")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new", new_chat))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.success("✅ Бот запущен и готов к работе")
    application.run_polling()

if __name__ == '__main__':
    main()