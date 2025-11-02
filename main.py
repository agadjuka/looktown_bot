import os
import sys
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from aiohttp import web
import aiohttp
from service_factory import get_yandex_agent_service
from src.services.logger_service import logger

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # Если не задан, будет получен автоматически
WEBHOOK_PATH = os.getenv('WEBHOOK_PATH', '/webhook')  # Путь для webhook
WEBAPP_HOST = os.getenv('WEBAPP_HOST', '0.0.0.0')
WEBAPP_PORT = int(os.getenv('PORT', '8080'))
CONTAINER_NAME = os.getenv('CONTAINER_NAME', 'ai-agent-ket')  # Имя контейнера для получения URL

# Глобальная переменная для приложения Telegram
application = None

async def send_to_agent(message_text, chat_id):
    """Отправка сообщения агенту через Responses API"""
    try:
        logger.agent("Обработка сообщения", chat_id)
        yandex_agent_service = get_yandex_agent_service()
        response = yandex_agent_service.send_to_agent(chat_id, message_text)
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
        yandex_agent_service.reset_context(chat_id)
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

async def health_check(request):
    """Health check endpoint для Serverless Container"""
    return web.json_response({"status": "ok", "service": "telegram-bot"})

async def handle_webhook(request):
    """Обработчик webhook от Telegram"""
    global application
    try:
        if not application:
            logger.error("Приложение Telegram не инициализировано")
            return web.json_response({"ok": False, "error": "Application not initialized"}, status=500)
        
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return web.json_response({"ok": True})
    except Exception as e:
        logger.error("Ошибка при обработке webhook", str(e))
        return web.json_response({"ok": False, "error": str(e)}, status=500)

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

async def get_container_url() -> str:
    """Получение URL контейнера через метаданные Yandex Cloud"""
    try:
        # Пытаемся получить URL через метаданные контейнера
        async with aiohttp.ClientSession() as session:
            # Метод 1: через метаданные (если доступны)
            metadata_url = "http://169.254.169.254/computeMetadata/v1/instance/network-interfaces/0/external-ip"
            try:
                async with session.get(metadata_url, headers={"Metadata-Flavor": "Google"}, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    if resp.status == 200:
                        ip = await resp.text()
                        # Но IP не даст нам домен, нужен другой способ
            except:
                pass
            
            # Метод 2: пытаемся получить из переменной окружения, которую установит GitHub Actions
            # или используем заголовок Host из первого запроса
            return None
    except Exception as e:
        logger.debug(f"Не удалось получить URL из метаданных: {str(e)}")
        return None

async def on_startup(app):
    """Выполняется при запуске веб-сервера"""
    global application
    logger.info("📡 Настройка webhook...")
    
    if not application:
        logger.error("⚠️ Приложение Telegram не инициализировано")
        return
    
    # Инициализируем и запускаем приложение Telegram (без polling)
    await application.initialize()
    await application.start()
    
    # Определяем webhook URL
    webhook_base_url = WEBHOOK_URL
    
    if not webhook_base_url:
        logger.info("🔍 WEBHOOK_URL не задан, пытаемся получить автоматически...")
        # Пытаемся получить URL из метаданных (обычно не работает для Serverless Containers)
        webhook_base_url = await get_container_url()
        
        if not webhook_base_url:
            logger.warning("⚠️ Не удалось получить URL контейнера автоматически")
            logger.warning("⚠️ Webhook будет установлен при первом запросе или через GitHub Actions")
            logger.info("💡 Webhook можно установить вручную после получения URL контейнера")
            # Не устанавливаем webhook сейчас, но бот будет работать
            # Webhook можно установить позже через API Telegram
    
    if webhook_base_url:
        webhook_url = f"{webhook_base_url.rstrip('/')}{WEBHOOK_PATH}"
        try:
            await application.bot.set_webhook(url=webhook_url)
            logger.success(f"✅ Webhook установлен: {webhook_url}")
        except Exception as e:
            logger.error(f"❌ Ошибка при установке webhook: {str(e)}")
            logger.warning("⚠️ Бот будет работать, но обновления не будут приходить до установки webhook")
    else:
        logger.info("ℹ️ Бот запущен, webhook будет установлен автоматически после деплоя")
    
    # Проверяем подключение к YDB при старте (lazy инициализация при первом запросе)
    try:
        logger.info("🔍 Проверка сервисов...")
        # Пробуем получить сервис для проверки
        get_yandex_agent_service()
        logger.success("✅ Все сервисы готовы")
    except Exception as e:
        logger.warning(f"⚠️ Предупреждение при инициализации сервисов: {str(e)}")
        import traceback
        logger.warning(f"Детали ошибки:\n{traceback.format_exc()}")
        logger.warning("⚠️ Сервисы будут инициализированы при первом запросе")

async def on_shutdown(app):
    """Выполняется при остановке веб-сервера"""
    global application
    logger.info("🛑 Остановка бота...")
    if application:
        try:
            await application.stop()
            await application.shutdown()
            await application.bot.delete_webhook()
        except Exception as e:
            logger.warning(f"Ошибка при остановке: {str(e)}")
    logger.success("✅ Бот остановлен")

def create_web_app():
    """Создание веб-приложения aiohttp"""
    app = web.Application()
    
    # Health check endpoint (обязателен для Serverless Container)
    app.router.add_get('/health', health_check)
    app.router.add_get('/', health_check)  # Также на корневой путь
    
    # Webhook endpoint для Telegram
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    
    # Обработчики жизненного цикла
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    
    return app

def main():
    """Основная функция запуска бота через webhook"""
    # Немедленно выводим информацию о запуске (до любых операций)
    print("=" * 60, flush=True)
    print("🚀 ЗАПУСК TELEGRAM BOT В КОНТЕЙНЕРЕ", flush=True)
    print("=" * 60, flush=True)
    
    try:
        logger.info("🚀 Запуск бота через webhook для контейнера")
        
        # Проверяем обязательные переменные окружения с детальным логированием
        logger.info("🔍 Проверка переменных окружения...")
        
        if not TELEGRAM_TOKEN:
            logger.error("❌ TELEGRAM_BOT_TOKEN не задан в переменных окружения")
            logger.error("❌ Бот не может запуститься без токена")
            sys.stderr.flush()
            sys.stdout.flush()
            sys.exit(1)
        else:
            logger.success("✅ TELEGRAM_BOT_TOKEN найден")
        
        # Проверяем другие важные переменные (но не критичные для старта)
        missing_vars = []
        if not os.getenv('YDB_ENDPOINT'):
            missing_vars.append('YDB_ENDPOINT')
        if not os.getenv('YDB_DATABASE'):
            missing_vars.append('YDB_DATABASE')
        if missing_vars:
            logger.warning(f"⚠️ Не заданы переменные: {', '.join(missing_vars)}")
            logger.warning("⚠️ Эти переменные потребуются при первом запросе")
        
        logger.info("✅ Базовые проверки пройдены")
        
        # Настраиваем приложение Telegram
        logger.info("🔧 Настройка приложения Telegram...")
        try:
            setup_application()
            logger.success("✅ Приложение Telegram настроено")
        except Exception as e:
            logger.error(f"❌ Ошибка при настройке приложения Telegram: {str(e)}")
            import traceback
            logger.error(f"Трассировка:\n{traceback.format_exc()}")
            sys.stderr.flush()
            sys.stdout.flush()
            raise
        
        # Создаем веб-приложение
        logger.info("🌐 Создание веб-приложения...")
        try:
            web_app = create_web_app()
            logger.success("✅ Веб-приложение создано")
        except Exception as e:
            logger.error(f"❌ Ошибка при создании веб-приложения: {str(e)}")
            import traceback
            logger.error(f"Трассировка:\n{traceback.format_exc()}")
            sys.stderr.flush()
            sys.stdout.flush()
            raise
        
        logger.success(f"✅ Бот готов к запуску на {WEBAPP_HOST}:{WEBAPP_PORT}")
        logger.info(f"📡 Webhook путь: {WEBHOOK_PATH}")
        logger.info(f"🏥 Health check: http://{WEBAPP_HOST}:{WEBAPP_PORT}/health")
        logger.info(f"🏥 Health check: http://{WEBAPP_HOST}:{WEBAPP_PORT}/")
        print("=" * 60, flush=True)
        print("✅ ВЕБ-СЕРВЕР ЗАПУСКАЕТСЯ", flush=True)
        print("=" * 60, flush=True)
        
        # Запускаем веб-сервер
        try:
            web.run_app(web_app, host=WEBAPP_HOST, port=WEBAPP_PORT)
        except Exception as e:
            logger.error(f"❌ Ошибка при запуске веб-сервера: {str(e)}")
            import traceback
            logger.error(f"Трассировка:\n{traceback.format_exc()}")
            sys.stderr.flush()
            sys.stdout.flush()
            raise
        
    except KeyboardInterrupt:
        logger.info("⚠️ Получен сигнал остановки (KeyboardInterrupt)")
        sys.stderr.flush()
        sys.stdout.flush()
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА ПРИ ЗАПУСКЕ: {str(e)}")
        import traceback
        logger.error(f"Полная трассировка:\n{traceback.format_exc()}")
        print("=" * 60, file=sys.stderr, flush=True)
        print("❌ БОТ НЕ ЗАПУЩЕН ИЗ-ЗА ОШИБКИ", file=sys.stderr, flush=True)
        print("=" * 60, file=sys.stderr, flush=True)
        sys.stderr.flush()
        sys.stdout.flush()
        sys.exit(1)
    finally:
        print("=" * 60, flush=True)
        logger.info("🔄 Завершение работы...")
        if application:
            logger.info("🔄 Очистка ресурсов...")
        sys.stderr.flush()
        sys.stdout.flush()

if __name__ == '__main__':
    # Обработка всех неперехваченных исключений
    try:
        main()
    except KeyboardInterrupt:
        logger.info("⚠️ Получен сигнал остановки (KeyboardInterrupt)")
        sys.exit(0)
    except Exception as e:
        # Критическая ошибка, которую не поймал try-except в main()
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {str(e)}")
        import traceback
        logger.error(f"Трассировка:\n{traceback.format_exc()}")
        sys.stderr.flush()
        sys.stdout.flush()
        sys.exit(1)

