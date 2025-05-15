import sys
import os
sys.path.append(os.path.abspath("/app"))

from main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_get_forecast(mocker):
    # Мокаем os.getenv для OPENWEATHERMAP_API_KEY
    mocker.patch("os.getenv", return_value="dummy-api-key")
    response = client.get("/forecast/Moscow?lang=ru")
    assert response.status_code == 200
    assert "city" in response.json()