from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
import os
import redis
from dotenv import load_dotenv
import time
import logging
from collections import Counter
from statistics import mean
from datetime import datetime
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter as PrometheusCounter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8081"],  # Разрешаем запросы с фронтенда
    allow_credentials=True,
    allow_methods=["*"],  # Разрешаем все методы (GET, POST, etc.)
    allow_headers=["*"],  # Разрешаем все заголовки
)

Instrumentator().instrument(app).expose(app)
redis_cache_hits = PrometheusCounter(
    name='redis_cache_hits_total',
    documentation='Total number of Redis cache hits'
)
redis_cache_misses = PrometheusCounter(
    name='redis_cache_misses_total',
    documentation='Total number of Redis cache misses'
)
openweather_requests = PrometheusCounter(
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

try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    redis_client.ping()
    logger.info(f"Successfully connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
except redis.exceptions.ConnectionError as e:
    logger.error(f"Failed to connect to Redis at {REDIS_HOST}:{REDIS_PORT} - {e}")
    raise RuntimeError(f"Failed to connect to Redis: {e}")

@app.get("/forecast/{city}")
async def get_forecast(city: str, lang: str = "en", days: int = None):
    logger.info(f"Received request: city={city}, lang={lang}, days={days}")
    cache_key = f"forecast:{city}:{lang}:{days or 'current'}"
    cached_data = None
    country_code = "N/A"
    try:
        cached_data = redis_client.get(cache_key)
    except redis.exceptions.ConnectionError as e:
        logger.warning(f"Redis connection error on GET: {e}. Proceeding without cache.")

    result = None
    forecast_list = None
    city_name = city

    if cached_data:
        logger.info(f"Cache hit: {cache_key}")
        redis_cache_hits.inc()
        try:
            import ast
            cached_result = ast.literal_eval(cached_data)
            forecast_list = cached_result["forecast"]
            city_name = cached_result.get("city", city)
            country_code = cached_result.get("country", "N/A")
            result = {"city": city_name, "forecast": forecast_list, "country": country_code, "fromCache": True}
        except (ValueError, SyntaxError) as e:
            logger.error(f"Error parsing cached data for {cache_key}: {e}. Fetching fresh data.")
            cached_data = None
            try:
                redis_client.delete(cache_key)
            except redis.exceptions.ConnectionError as redis_err:
                logger.warning(f"Redis connection error on DELETE: {redis_err}.")

    if not cached_data:
        logger.info(f"Cache miss or invalid cache data: fetching from OpenWeatherMap for {city}")
        redis_cache_misses.inc()
        params = {"q": city, "appid": OPENWEATHERMAP_API_KEY, "units": "metric", "lang": lang}
        try:
            response = requests.get("http://api.openweathermap.org/data/2.5/forecast", params=params)
            openweather_requests.inc()
            response.raise_for_status()
            logger.info(f"OpenWeatherMap response status: {response.status_code} for city {city}")
        except requests.exceptions.RequestException as e:
            logger.error(f"OpenWeatherMap request failed for city {city}: {e}")
            if isinstance(e, requests.exceptions.HTTPError) and e.response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"City '{city}' not found by OpenWeatherMap")
            raise HTTPException(status_code=503, detail="Failed to fetch weather data from provider")

        data = response.json()
        if not data.get("list"):
            logger.error(f"No forecast data ('list') in OpenWeatherMap response for city {city}")
            raise HTTPException(status_code=404, detail=f"No forecast data available for city '{city}'")

        # Группируем данные по дням и выбираем одну запись на день (ближайшую к 12:00)
        forecast_dict = {}
        for item in data["list"]:
            forecast_date = datetime.strptime(item["dt_txt"], "%Y-%m-%d %H:%M:%S")
            day_key = forecast_date.strftime("%Y-%m-%d")
            if day_key not in forecast_dict:
                forecast_dict[day_key] = item
            # Выбираем запись ближе к 12:00 (индекс 11:00-13:00)
            current_hour = forecast_date.hour
            existing_hour = datetime.strptime(forecast_dict[day_key]["dt_txt"], "%Y-%m-%d %H:%M:%S").hour
            if abs(12 - current_hour) < abs(12 - existing_hour):
                forecast_dict[day_key] = item

        # Преобразуем в список, ограничиваем по дням
        forecast_list = [
            {
                "date": item["dt_txt"],
                "temperature": item["main"]["temp"],
                "description": item["weather"][0]["description"],
                "icon": item["weather"][0]["icon"]
            }
            for day, item in forecast_dict.items()
        ]
        days_limit = days if days else 7  # По умолчанию 7 дней
        if len(forecast_list) > days_limit:
            forecast_list = forecast_list[:days_limit]

        city_name = data.get("city", {}).get("name", city)
        country_code = data.get("city", {}).get("country", "N/A")
        result = {"city": city_name, "forecast": forecast_list, "country": country_code, "fromCache": False}

        try:
            cache_data = {"city": city_name, "forecast": forecast_list, "country": country_code}
            redis_client.setex(cache_key, 3600, str(cache_data))
            logger.info(f"Saved forecast for {city_name} to cache {cache_key}")
        except redis.exceptions.ConnectionError as e:
            logger.warning(f"Redis connection error on SETEX: {e}. Proceeding without caching.")

    if forecast_list:
        try:
            first_day_str = forecast_list[0]["date"].split(" ")[0]
            first_day_forecasts = [f for f in forecast_list if f["date"].startswith(first_day_str)]

            if not first_day_forecasts:
                logger.error(f"No forecasts found for the first day ({first_day_str}) in the list for city {city_name}")
                raise ValueError(f"No forecasts for the first day ({first_day_str})")

            avg_temperature = mean([f["temperature"] for f in first_day_forecasts])
            descriptions = Counter([f["description"] for f in first_day_forecasts])
            most_common_description = descriptions.most_common(1)[0][0]
            icon = first_day_forecasts[0]["icon"]

            logger.info(f"Aggregated data for {city_name}: avg_temp={avg_temperature:.2f}, descr='{most_common_description}', icon='{icon}'")

            history_entry = {
                "city": city_name,
                "forecast_date": first_day_str,
                "avg_temperature": round(avg_temperature, 2),
                "description": most_common_description,
                "icon": icon,
                "request_time": datetime.utcnow().isoformat() + "Z"
            }
            try:
                redis_client.lpush("weather_history", str(history_entry))
                redis_client.ltrim("weather_history", 0, 99)
                logger.info(f"Saved history entry for {city_name}")
            except redis.exceptions.ConnectionError as e:
                logger.warning(f"Redis connection error on LPUSH/LTRIM: {e}. History not saved.")

        except Exception as e:
            logger.error(f"Failed to aggregate forecast data or save history for {city_name}: {e}", exc_info=True)

    if result is None:
        logger.error(f"Result is unexpectedly None at the end of get_forecast for city {city}")
        raise HTTPException(status_code=500, detail="Internal server error processing request.")

    return result

@app.get("/weather_history")
async def get_weather_history(limit: int = 10):
    limit = min(max(1, limit), 100)
    logger.info(f"Fetching weather history, limit={limit}")
    try:
        history_str = redis_client.lrange("weather_history", 0, limit - 1)
        import ast
        history = []
        for entry_str in history_str:
            try:
                history.append(ast.literal_eval(entry_str))
            except (ValueError, SyntaxError) as e:
                logger.warning(f"Could not parse history entry: {entry_str[:100]}... Error: {e}")

        logger.info(f"Fetched {len(history)} history records")
        return {"history": history}
    except redis.exceptions.ConnectionError as e:
        logger.error(f"Redis connection error while fetching history: {e}")
        raise HTTPException(status_code=503, detail="Cache service unavailable")
    except Exception as e:
        logger.error(f"Failed to fetch or parse weather history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch weather history")