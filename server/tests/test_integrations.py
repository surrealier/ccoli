from src.integrations import IntegrationRegistry, WeatherIntegration


class _DummyResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_weather_integration_missing_key():
    weather = WeatherIntegration(api_key="")
    result = weather.execute("weather.current")
    assert result.ok is False
    assert result.error is not None
    assert result.error.code.value == "AUTH_MISSING_KEY"


def test_weather_integration_success(monkeypatch):
    payload = {
        "name": "Seoul",
        "weather": [{"description": "맑음"}],
        "main": {"temp": 23, "feels_like": 24, "humidity": 40},
        "wind": {"speed": 1.2},
    }

    def _fake_get(*args, **kwargs):
        return _DummyResp(200, payload)

    import requests

    monkeypatch.setattr(requests, "get", _fake_get)
    weather = WeatherIntegration(api_key="abc")
    result = weather.execute("weather.current")
    assert result.ok is True
    assert result.data["city"] == "Seoul"


def test_registry_enable_disable():
    registry = IntegrationRegistry()
    weather = WeatherIntegration(api_key="abc")
    registry.register(weather, enabled=False)
    assert registry.execute("weather", "weather.current") is None
    assert registry.set_enabled("weather", True) is True
