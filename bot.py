import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from service_factory import get_yandex_agent_service
from src.services.logger_service import logger

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

async def send_to_agent(message_text, chat_id):
    """Отправка сообщения агенту через Responses API"""
    try:
        logger.agent("Обработка сообщения", chat_id)
        yandex_agent_service = get_yandex_agent_service()
        response = await yandex_agent_service.send_to_agent(chat_id, message_text)
        logger.agent("Ответ получен", chat_id)
        return response
    except Exception as e:
        logger.error("Ошибка при обращении к агенту", str(e))
        return {"user_message": f"Ошибка при обращении к агенту: {str(e)}"}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    chat_id = str(update.effective_chat.id)
    logger.telegram("Команда /start", chat_id)
    await update.message.reply_text('Привет! Я тестовый бот с интеграцией Яндекс.АИ. Отправь мне любое сообщение.')

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
    await update.message.reply_text(user_message_text, parse_mode=ParseMode.MARKDOWN)

    # Временная заглушка: отправляем alert менеджера тем же пользователю вторым сообщением
    if isinstance(agent_response, dict) and agent_response.get("manager_alert"):
        await update.message.reply_text(agent_response["manager_alert"], parse_mode=ParseMode.MARKDOWN)
    logger.telegram("Ответ отправлен", chat_id)

def main():
    """Основная функция запуска бота"""
    logger.info("🚀 Запуск бота с Responses API")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new", new_chat))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.success("✅ Бот запущен и готов к работе")
    application.run_polling()

if __name__ == '__main__':
    main()