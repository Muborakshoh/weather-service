import sys
import os
sys.path.append(os.path.abspath("/app"))  # Явно добавляем /app в путь поиска

from main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def test_get_forecast():
    response = client.get("/forecast/Moscow?lang=ru")
    assert response.status_code == 200
    assert "city" in response.json()