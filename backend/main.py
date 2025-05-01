from fastapi import FastAPI, HTTPException
import requests
import os
import redis
from dotenv import load_dotenv
import time
import logging
from collections import Counter # Оставляем стандартный Counter как есть
from statistics import mean
from datetime import datetime
from prometheus_fastapi_instrumentator import Instrumentator
# Переименовываем импорт Counter из prometheus_client
from prometheus_client import Counter as PrometheusCounter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()

# Инициализация Prometheus метрик с использованием переименованного класса
Instrumentator().instrument(app).expose(app)
redis_cache_hits = PrometheusCounter( # Используем PrometheusCounter
    name='redis_cache_hits_total',
    documentation='Total number of Redis cache hits'
)
redis_cache_misses = PrometheusCounter( # Используем PrometheusCounter
    name='redis_cache_misses_total',
    documentation='Total number of Redis cache misses'
)
openweather_requests = PrometheusCounter( # Используем PrometheusCounter
    name='openweather_requests_total',
    documentation='Total number of requests to OpenWeatherMap'
)

OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")

logger.info(f"Environment variables: REDIS_HOST={REDIS_HOST}, REDIS_PORT={REDIS_PORT}")

if not OPENWEATHERMAP_API_KEY:
    logger.error("OPENWEATHERMAP_API_KEY environment variable is not set")
    raise ValueError("OPENWEATHERMAP_API_KEY environment variable is not set")

# Добавляем проверку соединения с Redis при старте (опционально, но полезно)
try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    redis_client.ping()
    logger.info(f"Successfully connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except redis.exceptions.ConnectionError as e:
    logger.error(f"Failed to connect to Redis at {REDIS_HOST}:{REDIS_PORT} - {e}")
    # В зависимости от требований, можно либо выйти, либо продолжить без кэша
    raise RuntimeError(f"Failed to connect to Redis: {e}")


@app.get("/forecast/{city}")
async def get_forecast(city: str, lang: str = "en"):
    logger.info(f"Received request: city={city}, lang={lang}")
    cache_key = f"forecast:{city}:{lang}"
    cached_data = None
    try:
        cached_data = redis_client.get(cache_key)
    except redis.exceptions.ConnectionError as e:
        logger.warning(f"Redis connection error on GET: {e}. Proceeding without cache.")
        # Можно решить продолжать без кэша или вернуть ошибку
        # raise HTTPException(status_code=503, detail="Cache service unavailable")

    # Переменные для результата
    result = None
    forecast_list = None
    city_name = city # Инициализируем именем из запроса

    if cached_data:
        logger.info(f"Cache hit: {cache_key}")
        redis_cache_hits.inc()
        try:
            # Используем ast.literal_eval вместо eval для безопасности
            import ast
            forecast_list = ast.literal_eval(cached_data)
            # Попробуем извлечь имя города из кэша, если оно там есть (хотя сейчас нет)
            # Если бы кэшировали весь result, можно было бы сделать так:
            # cached_result = ast.literal_eval(cached_data)
            # forecast_list = cached_result["forecast"]
            # city_name = cached_result.get("city", city) # Используем город из кэша или запроса
            result = {"city": city_name, "forecast": forecast_list, "fromCache": True}
        except (ValueError, SyntaxError) as e:
             logger.error(f"Error parsing cached data for {cache_key}: {e}. Fetching fresh data.")
             cached_data = None # Сбрасываем флаг, чтобы запросить свежие данные
             # Можно также удалить невалидный ключ из кэша
             try:
                 redis_client.delete(cache_key)
             except redis.exceptions.ConnectionError as redis_err:
                 logger.warning(f"Redis connection error on DELETE: {redis_err}.")


    if not cached_data: # Если кэш промахнулся ИЛИ данные из кэша невалидны
        logger.info(f"Cache miss or invalid cache data: fetching from OpenWeatherMap for {city}")
        redis_cache_misses.inc() # Считаем промах только если реально идем в API
        params = {"q": city, "appid": OPENWEATHERMAP_API_KEY, "units": "metric", "lang": lang}
        try:
            response = requests.get("http://api.openweathermap.org/data/2.5/forecast", params=params)
            openweather_requests.inc()
            response.raise_for_status() # Проверяет на 4xx/5xx ошибки
            logger.info(f"OpenWeatherMap response status: {response.status_code} for city {city}")
        except requests.exceptions.RequestException as e:
            logger.error(f"OpenWeatherMap request failed for city {city}: {e}")
            # Проверяем, был ли это 404 от OpenWeatherMap
            if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 404:
                 raise HTTPException(status_code=404, detail=f"City '{city}' not found by OpenWeatherMap")
            raise HTTPException(status_code=503, detail="Failed to fetch weather data from provider") # 503 Service Unavailable

        # response.status_code == 200 проверять не нужно после raise_for_status()
        data = response.json()
        # logger.info(f"OpenWeatherMap response data: {data}") # Логировать весь ответ может быть избыточно
        if not data.get("list"):
            logger.error(f"No forecast data ('list') in OpenWeatherMap response for city {city}")
            # Это маловероятно после успешного 200, но лучше проверить
            raise HTTPException(status_code=404, detail=f"No forecast data available for city '{city}'")

        forecast_list = [
            {
                "date": item["dt_txt"],
                "temperature": item["main"]["temp"],
                "description": item["weather"][0]["description"],
                "icon": item["weather"][0]["icon"]
            }
            for item in data["list"]
        ]
        city_name = data.get("city", {}).get("name", city) # Обновляем имя города из ответа API
        result = {"city": city_name, "forecast": forecast_list, "fromCache": False}

        try:
            # Используем str() для сохранения в Redis, как и было
            redis_client.setex(cache_key, 3600, str(forecast_list))
            logger.info(f"Saved forecast for {city_name} to cache {cache_key}")
        except redis.exceptions.ConnectionError as e:
            logger.warning(f"Redis connection error on SETEX: {e}. Proceeding without caching.")
            # Не прерываем запрос, просто не закэшировали

    # --- Агрегация данных и сохранение истории ---
    # Этот блок теперь выполняется только если forecast_list был успешно получен (из кэша или API)
    if forecast_list:
        try:
            # Находим дату первого дня
            if not forecast_list: # Доп. проверка на всякий случай
                 raise ValueError("Forecast list is empty before aggregation")

            first_day_str = forecast_list[0]["date"].split(" ")[0] # Берем 'YYYY-MM-DD' из первой записи
            first_day_forecasts = [
                f for f in forecast_list
                if f["date"].startswith(first_day_str)
            ]

            if not first_day_forecasts:
                # Это странная ситуация, если forecast_list не пуст
                logger.error(f"No forecasts found for the first day ({first_day_str}) in the list for city {city_name}")
                raise ValueError(f"No forecasts for the first day ({first_day_str})")

            avg_temperature = mean([f["temperature"] for f in first_day_forecasts])
            # Вот здесь используется Counter из collections, теперь он не перезаписан
            descriptions = Counter([f["description"] for f in first_day_forecasts])
            most_common_description = descriptions.most_common(1)[0][0]
            # Берем иконку первого прогноза дня (или можно тоже выбрать самую частую)
            icon = first_day_forecasts[0]["icon"]

            logger.info(f"Aggregated data for {city_name}: avg_temp={avg_temperature:.2f}, descr='{most_common_description}', icon='{icon}'")

            # Сохраняем историю запросов в Redis
            history_entry = {
                "city": city_name,
                "forecast_date": first_day_str, # Сохраняем только дату YYYY-MM-DD
                "avg_temperature": round(avg_temperature, 2), # Округляем для хранения
                "description": most_common_description,
                "icon": icon,
                "request_time": datetime.utcnow().isoformat() + "Z" # Добавляем Z для UTC
            }
            try:
                # Используем str() для сохранения в Redis, как и было
                redis_client.lpush("weather_history", str(history_entry))
                redis_client.ltrim("weather_history", 0, 99)  # Храним последние 100 записей
                logger.info(f"Saved history entry for {city_name}")
            except redis.exceptions.ConnectionError as e:
                 logger.warning(f"Redis connection error on LPUSH/LTRIM: {e}. History not saved.")

        except Exception as e:
            # Логируем ошибку агрегации, но НЕ прерываем основной запрос прогноза
            logger.error(f"Failed to aggregate forecast data or save history for {city_name}: {e}", exc_info=True)
            # Не поднимаем HTTPException здесь, чтобы пользователь все равно получил прогноз
            # Можно добавить метрику для ошибок агрегации/истории
    else:
         # Эта ветка не должна достигаться, если логика выше верна, но для полноты
         logger.error(f"Forecast list is unexpectedly empty before returning result for city {city}")
         raise HTTPException(status_code=500, detail="Internal error: could not process forecast data.")


    # Возвращаем результат, полученный из кэша или API
    if result is None:
        # Если дошли сюда и result все еще None, значит что-то пошло не так
        logger.error(f"Result is unexpectedly None at the end of get_forecast for city {city}")
        raise HTTPException(status_code=500, detail="Internal server error processing request.")

    return result


@app.get("/weather_history")
async def get_weather_history(limit: int = 10):
    # Ограничим максимальный лимит для безопасности
    limit = min(max(1, limit), 100) # от 1 до 100
    logger.info(f"Fetching weather history, limit={limit}")
    try:
        history_str = redis_client.lrange("weather_history", 0, limit - 1)
        # Преобразуем строки обратно в словари с безопасностью
        import ast
        history = []
        for entry_str in history_str:
            try:
                history.append(ast.literal_eval(entry_str))
            except (ValueError, SyntaxError) as e:
                 logger.warning(f"Could not parse history entry: {entry_str[:100]}... Error: {e}")
                 # Пропускаем невалидную запись

        logger.info(f"Fetched {len(history)} history records")
        return {"history": history}
    except redis.exceptions.ConnectionError as e:
         logger.error(f"Redis connection error while fetching history: {e}")
         raise HTTPException(status_code=503, detail="Cache service unavailable")
    except Exception as e:
        logger.error(f"Failed to fetch or parse weather history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch weather history")