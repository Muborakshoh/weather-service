import os
import json
import logging
from datetime import datetime
import requests
import redis
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = os.getenv("REDIS_PORT", 6379)

if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN environment variable is not set")
    raise ValueError("TELEGRAM_TOKEN environment variable is not set")

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

LOG_KEY = "bot_request_logs"

def log_request_response(user_id, request_data, response_data):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": user_id,
        "request": request_data,
        "response": response_data
    }
    try:
        
        redis_client.lpush(LOG_KEY, json.dumps(log_entry, ensure_ascii=False))
        
        redis_client.ltrim(LOG_KEY, 0, 999)
    except redis.RedisError as e:
        logger.error(f"Failed to log request/response to Redis: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = [
        [
            InlineKeyboardButton("Поиск погоды", callback_data="search_weather"),
            InlineKeyboardButton("История поиска", callback_data="show_history"),
        ],
        [InlineKeyboardButton("О боте", callback_data="about_bot")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = "Привет! Я бот для получения прогноза погоды. Выбери действие:"
    await update.message.reply_text(message, reply_markup=reply_markup)
    
    log_request_response(user_id, {"command": "/start"}, {"message": message})

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if query.data == "show_history":
        await show_history(update, context, from_callback=True)
    elif query.data == "about_bot":
        await about_bot(update, context, from_callback=True)
    elif query.data == "search_weather":
        await query.message.reply_text("Введите название города (например, Moscow):")
        log_request_response(user_id, {"action": "search_weather"}, {"message": "Введите название города"})

async def about_bot(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user_id = update.effective_user.id
    message = "Я бот для получения прогноза погоды! Используй кнопки, чтобы:\n- Узнать погоду по городу\n- Посмотреть историю поиска\nСоздан для проекта weather_service."
    if from_callback:
        await update.callback_query.message.reply_text(message)
    else:
        await update.message.reply_text(message)
    
    log_request_response(user_id, {"command": "/about"}, {"message": message})


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    user_id = update.effective_user.id
    try:
        response = requests.get(f"{BACKEND_URL}/weather_history", params={"limit": 14})
        response.raise_for_status()
        history = response.json().get("history", [])

        if not history:
            message = "История поиска пуста."
            if from_callback:
                await update.callback_query.message.reply_text(message)
            else:
                await update.message.reply_text(message)
            log_request_response(user_id, {"action": "show_history"}, {"message": message})
            return

        message = "История поиска:\n"
        for entry in history:
            message += f"Город: {entry['city']}\nДата прогноза: {entry['forecast_date']}\nТемпература: {entry['avg_temperature']:.1f}°C\nОписание: {entry['description']}\nВремя запроса: {entry['request_time']}\n\n"

        if from_callback:
            await update.callback_query.message.reply_text(message)
        else:
            await update.message.reply_text(message)
        
        log_request_response(user_id, {"action": "show_history"}, {"message": message})
    except requests.RequestException as e:
        logger.error(f"Failed to fetch history: {e}")
        message = "Не удалось загрузить историю поиска."
        if from_callback:
            await update.callback_query.message.reply_text(message)
        else:
            await update.message.reply_text(message)
        log_request_response(user_id, {"action": "show_history"}, {"message": message, "error": str(e)})


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    city = update.message.text.strip()
    lang = "ru" 

    try:
        response = requests.get(f"{BACKEND_URL}/forecast/{city}", params={"lang": lang})
        response.raise_for_status()
        data = response.json()

        message = f"Погода в {data['city']}:\n"
        for forecast in data["forecast"][:5]:  # Показываем первые 5 записей (1 день)
            message += f"Дата: {forecast['date']}\nТемпература: {forecast['temperature']}°C\nОписание: {forecast['description']}\n\n"
        message += f"Данные {'из кэша' if data['fromCache'] else 'от OpenWeatherMap'}"

        await update.message.reply_text(message)
        log_request_response(user_id, {"city": city, "lang": lang}, {"message": message})
    except requests.RequestException as e:
        logger.error(f"Failed to fetch weather for {city}: {e}")
        message = "Не удалось найти город. Попробуйте снова (например, Moscow)."
        await update.message.reply_text(message)
        log_request_response(user_id, {"city": city, "lang": lang}, {"message": message, "error": str(e)})

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("history", show_history))
    application.add_handler(CommandHandler("about", about_bot))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Starting Telegram bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()