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
    import asyncio
    from fastapi import FastAPI, Request, BackgroundTasks
    print("✅ FastAPI импортирован", flush=True)
except Exception as e:
    print(f"❌ Ошибка импорта FastAPI: {e}", flush=True)
    sys.exit(1)

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
    from telegram.constants import ParseMode
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

print("✅ ВСЕ ИМПОРТЫ УСПЕШНЫ", flush=True)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
WEBHOOK_PATH = os.getenv('WEBHOOK_PATH', '/webhook')

# Глобальная переменная для приложения Telegram
application = None

# Создаем FastAPI приложение
app = FastAPI(
    title="Looktown Bot",
    version="0.1.0"
)

async def send_to_agent(message_text, chat_id):
    """Отправка сообщения агенту через Responses API"""
    try:
        logger.agent("Обработка сообщения", chat_id)
        yandex_agent_service = get_yandex_agent_service()
        # Обертываем синхронный блокирующий вызов в thread executor, чтобы не блокировать event loop
        response = await asyncio.to_thread(yandex_agent_service.send_to_agent, chat_id, message_text)
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
        # Обертываем синхронный вызов в thread executor, чтобы не блокировать event loop
        await asyncio.to_thread(yandex_agent_service.reset_context, chat_id)
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

def setup_application():
    """Настройка приложения Telegram"""
    global application
    
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не задан в переменных окружения")
    
    logger.info("🚀 Инициализация бота с Responses API")
    
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new", new_chat))
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
    
    # Создаем key.json из переменной окружения, если нужно (как в entrypoint.sh)
    yc_sa_key_json = os.getenv('YC_SA_KEY_JSON')
    if yc_sa_key_json:
        print("📝 Создание key.json из переменной окружения...", flush=True)
        try:
            with open('/app/key.json', 'w') as f:
                f.write(yc_sa_key_json)
            os.environ['YANDEX_SERVICE_ACCOUNT_KEY_FILE'] = '/app/key.json'
            os.environ['YC_SERVICE_ACCOUNT_KEY_FILE'] = '/app/key.json'
            print("✅ key.json создан", flush=True)
        except Exception as e:
            print(f"⚠️ Ошибка создания key.json: {e}", flush=True)
    
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
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """Обработчик webhook от Telegram"""
    global application
    
    try:
        if not application:
            logger.error("Приложение Telegram не инициализировано")
            return {"ok": False, "error": "Application not initialized"}
        
        data = await request.json()
        update = Update.de_json(data, application.bot)
        
        # Обрабатываем update в фоне
        background_tasks.add_task(process_telegram_update, update)
        
        return {"ok": True}
    except Exception as e:
        logger.error("Ошибка при обработке webhook", str(e))
        return {"ok": False, "error": str(e)}

@app.post("/", tags=["Root"])
async def root_post(request: Request, background_tasks: BackgroundTasks):
    """
    POST обработчик для корневого пути.
    Может обрабатывать как обычные запросы, так и Telegram webhook.
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
            background_tasks.add_task(process_telegram_update, update)
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
