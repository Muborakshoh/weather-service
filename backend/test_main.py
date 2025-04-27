import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_get_weather_success():
    """Тест успешного получения погоды для существующего города."""
    response = client.get("/weather/London")
    assert response.status_code == 200
    json_response = response.json()
    assert "city" in json_response
    assert "temperature" in json_response
    assert "description" in json_response
    assert json_response["city"] == "London"

def test_get_weather_not_found():
    """Тест обработки несуществующего города."""
    response = client.get("/weather/NonExistentCity")
    assert response.status_code == 404
    assert response.json() == {"detail": "City not found"}