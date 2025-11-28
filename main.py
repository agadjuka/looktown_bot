import os
import sys

# Ранние логи ДО любых импортов (в stdout для Yandex Cloud)
print("=" * 60, flush=True)
print("🚀 НАЧАЛО ИМПОРТА МОДУЛЕЙ", flush=True)
print("=" * 60, flush=True)

try:
    from dotenv import load_dotenv
    print("✅ dotenv импортирован", flush=True)
except Exception as e:
    print(f"❌ Ошибка импорта dotenv: {e}", flush=True)
    sys.exit(1)

load_dotenv()
print("✅ .env загружен", flush=True)

try:
    from fastapi import FastAPI, Request
    print("✅ FastAPI импортирован", flush=True)
except Exception as e:
    print(f"❌ Ошибка импорта FastAPI: {e}", flush=True)
    sys.exit(1)

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    print("✅ telegram библиотеки импортированы", flush=True)
except Exception as e:
    print(f"❌ Ошибка импорта telegram: {e}", flush=True)
    sys.exit(1)

try:
    from service_factory import get_yandex_agent_service
    print("✅ service_factory импортирован", flush=True)
except Exception as e:
    print(f"❌ Ошибка импорта service_factory: {e}", flush=True)
    sys.exit(1)

try:
    from src.services.logger_service import logger
    print("✅ logger импортирован", flush=True)
except Exception as e:
    print(f"❌ Ошибка импорта logger: {e}", flush=True)
    sys.exit(1)

try:
    from src.config.admin_config import get_telegram_admin_group_id
    print("✅ admin_config импортирован", flush=True)
except Exception as e:
    print(f"⚠️ Ошибка импорта admin_config: {e}", flush=True)
    print("⚠️ Админ-панель будет недоступна", flush=True)

print("✅ ВСЕ ИМПОРТЫ УСПЕШНЫ", flush=True)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
WEBHOOK_PATH = os.getenv('WEBHOOK_PATH', '/webhook')

try:
    from src.handlers.telegram_handlers import start, new_chat, handle_message, get_admin_service
    print("✅ telegram_handlers импортирован", flush=True)
except Exception as e:
    print(f"❌ Ошибка импорта telegram_handlers: {e}", flush=True)
    sys.exit(1)

# Глобальная переменная для приложения Telegram
application = None

# Создаем FastAPI приложение
app = FastAPI(
    title="Looktown Bot",
    version="0.1.0"
)

async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает сообщения от админов в админской группе."""
    if not update.message:
        return

    message = update.message
    chat_id = update.effective_chat.id
    admin_group_id = get_telegram_admin_group_id()

    if admin_group_id is None or chat_id != admin_group_id:
        return
    if message.message_thread_id is None:
        return
    if message.from_user and message.from_user.is_bot:
        return
    if message.text and message.text.startswith("/"):
        return

    topic_id = message.message_thread_id

    try:
        admin_service = get_admin_service(context.bot)
        if admin_service is None:
            logger.warning("AdminPanelService не инициализирован. Сообщение не будет обработано.")
            return

        user_id = admin_service.storage.get_user_id(topic_id)
        if user_id is None:
            logger.warning("Не найден user_id для topic_id=%s. Сообщение не будет переслано.", topic_id)
            return

        mode = admin_service.storage.get_mode(user_id)

        if mode == "auto":
            await context.bot.send_message(
                chat_id=admin_group_id,
                text="⚠️ Включен автоматический режим. Сообщение не переслано клиенту.\n"
                     "Используйте команду /manager для переключения в ручной режим.",
                message_thread_id=topic_id,
                reply_to_message_id=message.message_id,
            )
        else:
            await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=admin_group_id,
                message_id=message.message_id,
            )
    except Exception as e:
        logger.error("Ошибка при пересылке сообщения от админа: %s", str(e), exc_info=True)

async def handle_manager_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /manager для включения ручного режима."""
    if not update.message:
        return

    message = update.message
    chat_id = update.effective_chat.id
    admin_group_id = get_telegram_admin_group_id()

    if admin_group_id is None or chat_id != admin_group_id:
        return
    if message.message_thread_id is None:
        return

    topic_id = message.message_thread_id

    try:
        admin_service = get_admin_service(context.bot)
        if admin_service is None:
            logger.warning("AdminPanelService не инициализирован. Команда /manager не выполнена.")
            return

        await admin_service.enable_manual_mode(topic_id)
    except Exception as e:
        logger.error("Ошибка при выполнении команды /manager: %s", str(e), exc_info=True)

async def handle_bot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /bot для включения автоматического режима."""
    if not update.message:
        return

    message = update.message
    chat_id = update.effective_chat.id
    admin_group_id = get_telegram_admin_group_id()

    if admin_group_id is None or chat_id != admin_group_id:
        return
    if message.message_thread_id is None:
        return

    topic_id = message.message_thread_id

    try:
        admin_service = get_admin_service(context.bot)
        if admin_service is None:
            logger.warning("AdminPanelService не инициализирован. Команда /bot не выполнена.")
            return

        await admin_service.enable_auto_mode(topic_id)
    except Exception as e:
        logger.error("Ошибка при выполнении команды /bot: %s", str(e), exc_info=True)

async def set_bot_commands(bot) -> None:
    """Устанавливает команды бота для разных групп пользователей."""
    try:
        from telegram import BotCommand
        try:
            from telegram import BotCommandScopeChat, BotCommandScopeDefault
        except ImportError:
            try:
                from telegram.constants import BotCommandScopeChat, BotCommandScopeDefault
            except ImportError:
                from telegram.helpers import BotCommandScopeChat, BotCommandScopeDefault
        
        default_commands = [BotCommand("new", "Сбросить историю переписки")]
        await bot.set_my_commands(commands=default_commands, scope=BotCommandScopeDefault())
        
        admin_group_id = get_telegram_admin_group_id()
        if admin_group_id is not None:
            admin_commands = [
                BotCommand("manager", "👨‍💻 Включить ручной режим"),
                BotCommand("bot", "🤖 Включить авто-режим ИИ"),
            ]
            await bot.set_my_commands(
                commands=admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_group_id),
            )
    except Exception as e:
        logger.error("Ошибка при установке команд бота: %s", str(e), exc_info=True)

def setup_application():
    """Настройка приложения Telegram"""
    global application
    
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в переменных окружения")
    
    logger.info("🚀 Инициализация бота с LangGraph")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new", new_chat))
    
    # Обработчики для админ-панели
    admin_group_id = get_telegram_admin_group_id()
    if admin_group_id is not None:
        admin_chat_filter = filters.Chat(chat_id=admin_group_id)
        application.add_handler(
            CommandHandler("manager", handle_manager_command, filters=admin_chat_filter)
        )
        application.add_handler(
            CommandHandler("bot", handle_bot_command, filters=admin_chat_filter)
        )
        application.add_handler(
            MessageHandler(admin_chat_filter & ~filters.COMMAND, handle_admin_message)
        )
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.success("✅ Бот инициализирован и готов к работе")

async def process_telegram_update(update: Update):
    """Обработка Telegram update"""
    global application
    if not application:
        logger.error("Приложение Telegram не инициализировано")
        return
    
    await application.process_update(update)

@app.on_event("startup")
async def startup_event():
    """Выполняется при запуске приложения"""
    # Логируем в stdout для гарантированной видимости
    print("╔═══════════════════════════════════════════════════════════", flush=True)
    print("║ 🚀 FastAPI startup: Приложение запускается...", flush=True)
    print("╚═══════════════════════════════════════════════════════════", flush=True)
    
    logger.info("╔═══════════════════════════════════════════════════════════")
    logger.info("║ 🚀 Приложение запускается...")
    logger.info("╚═══════════════════════════════════════════════════════════")
    
    # В Yandex Cloud Serverless Containers сервисный аккаунт используется автоматически
    # через метаданные (revision-service-account-id), файл key.json не требуется.
    # Код для создания key.json удален - используем автоматическую аутентификацию.
    print("✅ Используется автоматическая аутентификация через метаданные Yandex Cloud", flush=True)
    
    # Настраиваем приложение Telegram
    try:
        print("🔧 Настройка приложения Telegram...", flush=True)
        setup_application()
        print("✅ Приложение Telegram настроено", flush=True)
        
        # Инициализируем и запускаем приложение Telegram (без polling)
        print("🚀 Инициализация Telegram приложения...", flush=True)
        await application.initialize()
        await application.start()
        print("✅ Приложение Telegram запущено", flush=True)
        
        # Устанавливаем команды бота
        try:
            await set_bot_commands(application.bot)
            print("✅ Команды бота установлены", flush=True)
        except Exception as e:
            print(f"⚠️ Ошибка при установке команд бота: {e}", flush=True)
            logger.warning("Ошибка при установке команд бота: %s", str(e))
        
        logger.success("✅ Приложение Telegram запущено")
    except Exception as e:
        error_msg = f"❌ Ошибка при запуске приложения Telegram: {e}"
        print(error_msg, flush=True)
        import traceback
        tb = traceback.format_exc()
        print(f"Трассировка:\n{tb}", flush=True)
        logger.error(error_msg)
        logger.error(f"Трассировка:\n{tb}")
        # НЕ делаем raise - пусть приложение запустится даже с ошибкой
        # raise
    
    # Настраиваем webhook
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"
        try:
            await application.bot.set_webhook(url=webhook_url)
            logger.success(f"✅ Webhook установлен: {webhook_url}")
        except Exception as e:
            logger.error(f"❌ Ошибка при установке webhook: {str(e)}")
            logger.warning("⚠️ Бот будет работать, но обновления не будут приходить до установки webhook")
    else:
        logger.warning("⚠️ WEBHOOK_URL не задан, webhook не установлен")
        logger.info("💡 Webhook будет установлен автоматически через GitHub Actions или вручную")
    
    # Проверяем подключение к YDB при старте (lazy инициализация при первом запросе)
    try:
        logger.info("🔍 Проверка сервисов...")
        get_yandex_agent_service()
        logger.success("✅ Все сервисы готовы")
    except Exception as e:
        logger.warning(f"⚠️ Предупреждение при инициализации сервисов: {str(e)}")
        import traceback
        logger.warning(f"Детали ошибки:\n{traceback.format_exc()}")
        logger.warning("⚠️ Сервисы будут инициализированы при первом запросе")

@app.on_event("shutdown")
async def shutdown_event():
    """Выполняется при остановке приложения"""
    global application
    logger.info("🛑 Остановка бота...")
    if application:
        try:
            await application.stop()
            await application.shutdown()
            if WEBHOOK_URL:
                await application.bot.delete_webhook()
        except Exception as e:
            logger.warning(f"Ошибка при остановке: {str(e)}")
    logger.success("✅ Бот остановлен")

@app.get("/", tags=["Root"])
def root():
    """Корневой эндпоинт для проверки доступности сервиса"""
    return {
        "status": "OK",
        "message": "Looktown Bot is running",
        "version": "0.1.0",
        "service": "telegram-bot"
    }

@app.get("/health", tags=["Health Check"])
@app.get("/healthcheck", tags=["Health Check"])
def health_check():
    """Простой эндпоинт для проверки работоспособности сервиса"""
    return {
        "status": "OK",
        "service": "telegram-bot",
        "webhook": "enabled" if WEBHOOK_URL else "pending"
    }

@app.post(WEBHOOK_PATH, tags=["Telegram"])
async def webhook(request: Request):
    """Обработчик webhook от Telegram - ожидает завершения обработки"""
    global application
    
    try:
        if not application:
            logger.error("Приложение Telegram не инициализировано")
            return {"ok": False, "error": "Application not initialized"}
        
        data = await request.json()
        update = Update.de_json(data, application.bot)
        
        # ОЖИДАЕМ завершения обработки (как в рабочем проекте)
        # Event loop не блокируется, т.к. операции внутри асинхронные
        await process_telegram_update(update)
        
        # Возвращаем ответ только после полной обработки
        return {"ok": True}
    except Exception as e:
        logger.error("Ошибка при обработке webhook", str(e))
        return {"ok": False, "error": str(e)}

@app.post("/", tags=["Root"])
async def root_post(request: Request):
    """
    POST обработчик для корневого пути.
    Может обрабатывать как обычные запросы, так и Telegram webhook.
    Ожидает завершения обработки для Telegram updates.
    """
    try:
        # Пытаемся обработать как Telegram webhook
        data = await request.json()
        
        # Проверяем, что это Telegram update
        if "message" in data or "callback_query" in data:
            global application
            if not application:
                return {"status": "OK", "error": "Application not initialized"}
            
            update = Update.de_json(data, application.bot)
            # ОЖИДАЕМ завершения обработки (как в рабочем проекте)
            await process_telegram_update(update)
            return {"status": "ok"}
        else:
            # Если это не Telegram update, возвращаем обычный ответ
            return {
                "status": "OK",
                "message": "Looktown Bot is running",
                "version": "0.1.0"
            }
    except Exception as e:
        logger.error(f"❌ Ошибка обработки POST запроса: {e}")
        # В случае ошибки возвращаем обычный ответ
        return {
            "status": "OK",
            "message": "Looktown Bot is running",
            "version": "0.1.0"
        }

if __name__ == '__main__':
    import uvicorn
    
    # Проверяем обязательные переменные окружения
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не задан в переменных окружения")
        sys.exit(1)
    
    # Получаем хост и порт (для локального запуска)
    host = os.getenv('WEBAPP_HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '8080'))  # В контейнере порт фиксированный 8080
    
    logger.info(f"🚀 Запуск FastAPI сервера на {host}:{port}")
    print(f"🚀 Запуск FastAPI на {host}:{port}", flush=True)
    
    # Запускаем через uvicorn
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        log_level="info"
    )
