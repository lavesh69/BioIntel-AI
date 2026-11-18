"""Truthful provider-backed weather, AQI, geocoding, cache, and saved sites."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger("biointel.services.weather_environment")
STATUS_LIVE = "Live Weather"
STATUS_LIVE_FALLBACK = "Live Weather — Fallback Provider"
STATUS_CACHED = "Cached Weather"
STATUS_STALE_CACHED = "Stale Cached Weather"
STATUS_LOCATION_NOT_FOUND = "Location Not Found"
STATUS_PROVIDER_UNAVAILABLE = "Provider Unavailable"
STATUS_RATE_LIMITED = "Rate Limited"
STATUS_AUTH_REQUIRED = "Authentication Required"
STATUS_OFFLINE = "Offline"
STATUS_DATA_UNAVAILABLE = "Weather Data Unavailable"
WEATHER_PROVIDER = "Open-Meteo Forecast API"
AIR_QUALITY_PROVIDER = "Open-Meteo Air Quality API"
GEOCODING_PROVIDER = "Open-Meteo Geocoding API"
REVERSE_GEOCODING_PROVIDER = "OpenStreetMap Nominatim"
_COORDS = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?)\s*[, ]\s*([-+]?\d+(?:\.\d+)?)\s*$")


class ProviderRequestError(RuntimeError):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


def _num(value: Any, digits: int = 1) -> float | None:
    try:
        return None if value is None else round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _temp(value: Any, fahrenheit: bool) -> float | None:
    value = _num(value)
    return None if value is None else round(value * 9 / 5 + 32, 1) if fahrenheit else value


class WeatherEnvironmentEngine:
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
    GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
    AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
    REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"

    def __init__(
        self,
        workspace_root: str | Path | None = None,
        *,
        opener: Callable[..., Any] | None = None,
        now: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
        cache_ttl_seconds: int = 600,
        stale_after_seconds: int = 86_400,
    ) -> None:
        root = Path(workspace_root or os.environ.get("BIOINTEL_APP_HOME") or os.getcwd()).resolve()
        self.cache_dir = root / "UserData" / "cache" / "weather"
        self.location_store = root / "UserData" / "settings" / "weather_locations.json"
        self.cache_ttl_seconds = max(30, int(cache_ttl_seconds))
        self.stale_after_seconds = max(self.cache_ttl_seconds, int(stale_after_seconds))
        self._opener, self._now, self._sleep = opener or urllib.request.urlopen, now or time.time, sleeper or time.sleep
        self.last_geocode_status, self.last_geocode_error = "Not Requested", ""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.location_store.parent.mkdir(parents=True, exist_ok=True)

    @property
    def provider_registry(self) -> dict[str, dict[str, Any]]:
        alerts = os.environ.get("BIOINTEL_WEATHER_ALERTS_URL", "").strip()
        return {
            "geocoding": {"provider": GEOCODING_PROVIDER, "configured": True},
            "reverse_geocoding": {"provider": REVERSE_GEOCODING_PROVIDER, "configured": True},
            "weather_forecast": {"provider": WEATHER_PROVIDER, "configured": True, "cache_ttl_seconds": self.cache_ttl_seconds},
            "air_quality": {"provider": AIR_QUALITY_PROVIDER, "configured": True},
            "official_alerts": {"provider": "Configured authoritative adapter" if alerts else "None", "configured": bool(alerts)},
        }

    def _json(self, url: str, timeout: float, retries: int = 2) -> dict[str, Any]:
        if not url.startswith("https://"):
            raise ProviderRequestError(STATUS_PROVIDER_UNAVAILABLE, "Provider URL must use HTTPS.")
        message = "Provider request failed."
        for attempt in range(retries + 1):
            request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "BioIntelAI/15.6.0"})
            try:
                with self._opener(request, timeout=timeout) as response:
                    code = int(getattr(response, "status", 200))
                    if code == 429:
                        raise ProviderRequestError(STATUS_RATE_LIMITED, "Provider rate limit reached.")
                    if code in (401, 403):
                        raise ProviderRequestError(STATUS_AUTH_REQUIRED, "Provider authentication is required.")
                    if not 200 <= code < 300:
                        raise ProviderRequestError(STATUS_PROVIDER_UNAVAILABLE, f"Provider returned HTTP {code}.")
                    data = json.loads(response.read().decode("utf-8"))
                    if not isinstance(data, dict):
                        raise ProviderRequestError(STATUS_PROVIDER_UNAVAILABLE, "Invalid provider response.")
                    return data
            except ProviderRequestError:
                raise
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    raise ProviderRequestError(STATUS_RATE_LIMITED, "Provider rate limit reached.") from exc
                if exc.code in (401, 403):
                    raise ProviderRequestError(STATUS_AUTH_REQUIRED, "Provider authentication is required.") from exc
                message = f"Provider returned HTTP {exc.code}."
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                message = f"{type(exc).__name__}: provider request could not be completed."
            if attempt < retries:
                self._sleep(0.25 * 2**attempt)
        raise ProviderRequestError(STATUS_PROVIDER_UNAVAILABLE, message)

    @staticmethod
    def _coords(latitude: float, longitude: float) -> tuple[float, float]:
        lat, lon = float(latitude), float(longitude)
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("Latitude must be -90..90 and longitude -180..180.")
        return lat, lon

    def geocode_location_search(self, query: str) -> list[dict[str, Any]]:
        query = " ".join(str(query).strip().split())
        self.last_geocode_error = ""
        if not query:
            self.last_geocode_status = STATUS_LOCATION_NOT_FOUND
            return []
        match = _COORDS.match(query)
        if match:
            try:
                lat, lon = self._coords(*map(float, match.groups()))
            except ValueError as exc:
                self.last_geocode_status, self.last_geocode_error = STATUS_LOCATION_NOT_FOUND, str(exc)
                return []
            location = self.reverse_geocode(lat, lon) or {
                "name": f"{lat:.5f}, {lon:.5f}", "latitude": lat, "longitude": lon,
                "country": "", "admin1": "", "postal_code": "", "timezone": "UTC", "provider": "Manual coordinates",
            }
            self.last_geocode_status = "Coordinates Resolved"
            return [location]
        params = urllib.parse.urlencode({"name": query, "count": 10, "language": "en", "format": "json"})
        try:
            data = self._json(f"{self.GEOCODING_URL}?{params}", 5)
        except ProviderRequestError as exc:
            self.last_geocode_status, self.last_geocode_error = exc.status, str(exc)
            return []
        results = []
        for item in data.get("results", []):
            if not isinstance(item, dict):
                continue
            try:
                lat, lon = self._coords(item["latitude"], item["longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            parts = [str(item.get(key, "")).strip() for key in ("name", "admin1", "country")]
            results.append({
                "name": ", ".join(dict.fromkeys(x for x in parts if x)) or f"{lat:.5f}, {lon:.5f}",
                "latitude": lat, "longitude": lon, "country": str(item.get("country", "")),
                "country_code": str(item.get("country_code", "")), "admin1": str(item.get("admin1", "")),
                "postal_code": "", "timezone": str(item.get("timezone", "UTC")),
                "elevation_m": _num(item.get("elevation")), "provider": GEOCODING_PROVIDER,
            })
        self.last_geocode_status = "Location Matches Found" if results else STATUS_LOCATION_NOT_FOUND
        return results

    def reverse_geocode(self, latitude: float, longitude: float) -> dict[str, Any] | None:
        lat, lon = self._coords(latitude, longitude)
        params = urllib.parse.urlencode({"lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18})
        try:
            data = self._json(f"{self.REVERSE_URL}?{params}", 5, 1)
        except ProviderRequestError as exc:
            self.last_geocode_error = str(exc)
            return None
        address = data.get("address") if isinstance(data.get("address"), dict) else {}
        return {
            "name": str(data.get("display_name") or f"{lat:.5f}, {lon:.5f}"), "latitude": lat, "longitude": lon,
            "country": str(address.get("country", "")), "country_code": str(address.get("country_code", "")).upper(),
            "admin1": str(address.get("state") or address.get("region") or address.get("county") or ""),
            "postal_code": str(address.get("postcode", "")), "timezone": "UTC", "provider": REVERSE_GEOCODING_PROVIDER,
        }

    def _cache_path(self, lat: float, lon: float) -> Path:
        key = hashlib.sha256(f"{lat:.5f},{lon:.5f}".encode()).hexdigest()[:24]
        return self.cache_dir / f"weather_{key}.json"

    def invalidate_cache(self, latitude: float, longitude: float) -> bool:
        path = self._cache_path(*self._coords(latitude, longitude))
        if not path.exists():
            return False
        path.unlink()
        return True

    def _load_cache(self, lat: float, lon: float) -> tuple[dict[str, Any], float] | None:
        path = self._cache_path(lat, lon)
        if not path.is_file():
            return None
        try:
            wrapper = json.loads(path.read_text(encoding="utf-8"))
            payload, stamp = wrapper["payload"], float(wrapper["retrieved_epoch"])
            return (payload, max(0.0, self._now() - stamp)) if isinstance(payload, dict) else None
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _write_cache(self, lat: float, lon: float, payload: dict[str, Any]) -> None:
        path = self._cache_path(lat, lon)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps({"retrieved_epoch": self._now(), "payload": payload}), encoding="utf-8")
        temp.replace(path)

    def _forecast(self, lat: float, lon: float) -> dict[str, Any]:
        current = "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,snowfall,weather_code,cloud_cover,pressure_msl,wind_speed_10m,wind_direction_10m,wind_gusts_10m"
        hourly = "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,precipitation_probability,precipitation,rain,snowfall,weather_code,visibility,uv_index,wind_speed_10m,wind_direction_10m,wind_gusts_10m"
        daily = "weather_code,temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,sunrise,sunset,uv_index_max,precipitation_sum,rain_sum,snowfall_sum,precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max"
        params = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "current": current, "hourly": hourly, "daily": daily, "forecast_days": 7, "timezone": "auto"})
        data = self._json(f"{self.FORECAST_URL}?{params}", 7)
        if not isinstance(data.get("current"), dict) or not data["current"].get("time"):
            raise ProviderRequestError(STATUS_PROVIDER_UNAVAILABLE, "Weather response has no observation.")
        return data

    def _air_quality(self, lat: float, lon: float) -> dict[str, Any]:
        variables = "us_aqi,european_aqi,pm2_5,pm10,ozone,nitrogen_dioxide,sulphur_dioxide,carbon_monoxide"
        params = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "current": variables, "timezone": "auto"})
        try:
            current = self._json(f"{self.AIR_QUALITY_URL}?{params}", 6).get("current", {})
            if not current.get("time"):
                raise ProviderRequestError(STATUS_PROVIDER_UNAVAILABLE, "No current AQI model data.")
            aqi = _num(current.get("us_aqi"), 0)
            return {"available": True, "status": "Modelled Air Quality", "aqi_index": aqi,
                "aqi_category": self._aqi_category(aqi), "european_aqi": _num(current.get("european_aqi"), 0),
                "pm2_5_ug_m3": _num(current.get("pm2_5")), "pm10_ug_m3": _num(current.get("pm10")),
                "o3_ug_m3": _num(current.get("ozone")), "no2_ug_m3": _num(current.get("nitrogen_dioxide")),
                "so2_ug_m3": _num(current.get("sulphur_dioxide")), "co_ug_m3": _num(current.get("carbon_monoxide")),
                "observation_time": current.get("time"), "data_source": AIR_QUALITY_PROVIDER, "provenance": "Modelled"}
        except ProviderRequestError as exc:
            return {"available": False, "status": "Air Quality Data Unavailable", "aqi_index": None,
                "aqi_category": "Air Quality Data Unavailable", "data_source": AIR_QUALITY_PROVIDER,
                "provenance": "Unavailable", "error": str(exc)}
    def _alerts(self, lat: float, lon: float) -> tuple[list[dict[str, Any]], str]:
        endpoint = os.environ.get("BIOINTEL_WEATHER_ALERTS_URL", "").strip()
        if not endpoint:
            return [], "Official Weather Alerts Unavailable"
        try:
            separator = "&" if "?" in endpoint else "?"
            data = self._json(endpoint + separator + urllib.parse.urlencode({"latitude": lat, "longitude": lon}), 6, 1)
        except ProviderRequestError:
            return [], "Official Weather Alerts Unavailable"
        alerts = []
        for item in data.get("alerts", []):
            if isinstance(item, dict):
                alerts.append({
                    "issuing_authority": item.get("issuing_authority") or item.get("senderName"),
                    "severity": item.get("severity"), "affected_area": item.get("affected_area") or item.get("areaDesc"),
                    "issue_time": item.get("issue_time") or item.get("sent"), "effective": item.get("effective"),
                    "expires": item.get("expires"), "description": item.get("description"),
                    "source": item.get("source") or endpoint,
                })
        return alerts, "Official Weather Alerts Available" if alerts else "No Active Official Alerts"

    def fetch_weather_and_forecast(
        self,
        latitude: float,
        longitude: float,
        location_name: str = "Custom Location",
        unit_temp: str = "Celsius",
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        lat, lon = self._coords(latitude, longitude)
        fahrenheit = str(unit_temp).lower().startswith("f")
        unit = "°F" if fahrenheit else "°C"
        cached = self._load_cache(lat, lon)
        raw, age, status, error = None, None, STATUS_LIVE, ""
        if cached and not force_refresh and cached[1] <= self.cache_ttl_seconds:
            raw, age, status = cached[0], cached[1], STATUS_CACHED
        else:
            try:
                raw = self._forecast(lat, lon)
                self._write_cache(lat, lon, raw)
                age = 0.0
            except ProviderRequestError as exc:
                status, error = exc.status, str(exc)
                if cached:
                    raw, age = cached
                    status = STATUS_CACHED if age <= self.stale_after_seconds else STATUS_STALE_CACHED
        if raw is None:
            return self._unavailable(lat, lon, location_name, unit, status, error)
        current, hourly, daily = raw.get("current", {}), raw.get("hourly", {}), raw.get("daily", {})
        times = list(hourly.get("time", []))
        observed = str(current.get("time", ""))
        start = next((i for i, value in enumerate(times) if str(value) >= observed), 0)

        def series_value(block: dict[str, Any], key: str, index: int) -> Any:
            values = block.get(key, [])
            return values[index] if isinstance(values, list) and index < len(values) else None

        def h(key: str, index: int = start) -> Any:
            return series_value(hourly, key, index)

        convert = lambda value: _temp(value, fahrenheit)
        current_result = {
            "temperature": convert(current.get("temperature_2m")),
            "feels_like": convert(current.get("apparent_temperature")), "unit": unit,
            "humidity_pct": _num(current.get("relative_humidity_2m"), 0),
            "pressure_hpa": _num(current.get("pressure_msl")),
            "precipitation_mm": _num(current.get("precipitation")), "rain_mm": _num(current.get("rain")),
            "snowfall_cm": _num(current.get("snowfall")), "wind_speed_kmh": _num(current.get("wind_speed_10m")),
            "wind_direction_deg": _num(current.get("wind_direction_10m"), 0),
            "wind_gusts_kmh": _num(current.get("wind_gusts_10m")),
            "visibility_km": _num(float(h("visibility")) / 1000 if h("visibility") is not None else None),
            "cloud_cover_pct": _num(current.get("cloud_cover"), 0), "uv_index": _num(h("uv_index")),
            "weather_condition": self._wmo(current.get("weather_code")), "observation_time": observed or None,
            "sunrise": series_value(daily, "sunrise", 0), "sunset": series_value(daily, "sunset", 0),
        }
        hourly_result = []
        for index in range(start, min(len(times), start + 24)):
            hourly_result.append({
                "time": times[index], "temperature": convert(h("temperature_2m", index)),
                "feels_like": convert(h("apparent_temperature", index)), "dew_point": convert(h("dew_point_2m", index)),
                "humidity_pct": _num(h("relative_humidity_2m", index), 0),
                "precip_probability": _num(h("precipitation_probability", index), 0),
                "precipitation_mm": _num(h("precipitation", index)), "rain_mm": _num(h("rain", index)),
                "snowfall_cm": _num(h("snowfall", index)), "wind_speed_kmh": _num(h("wind_speed_10m", index)),
                "wind_direction_deg": _num(h("wind_direction_10m", index), 0),
                "wind_gusts_kmh": _num(h("wind_gusts_10m", index)), "uv_index": _num(h("uv_index", index)),
                "condition": self._wmo(h("weather_code", index)),
            })
        daily_result = []
        for index, day in enumerate(list(daily.get("time", []))[:7]):
            d = lambda key: series_value(daily, key, index)
            date_humidity = [_num(h("relative_humidity_2m", i)) for i, value in enumerate(times) if str(value)[:10] == str(day)]
            date_humidity = [value for value in date_humidity if value is not None]
            daily_result.append({
                "date": day, "temp_max": convert(d("temperature_2m_max")), "temp_min": convert(d("temperature_2m_min")),
                "feels_like_max": convert(d("apparent_temperature_max")), "feels_like_min": convert(d("apparent_temperature_min")),
                "condition": self._wmo(d("weather_code")),
                "precip_probability_max": _num(d("precipitation_probability_max"), 0),
                "precipitation_mm": _num(d("precipitation_sum")), "rain_mm": _num(d("rain_sum")),
                "snowfall_cm": _num(d("snowfall_sum")), "wind_speed_max_kmh": _num(d("wind_speed_10m_max")),
                "wind_gusts_max_kmh": _num(d("wind_gusts_10m_max")),
                "humidity_avg_pct": round(sum(date_humidity) / len(date_humidity), 0) if date_humidity else None,
                "uv_index_max": _num(d("uv_index_max")), "sunrise": d("sunrise"), "sunset": d("sunset"),
            })
        alerts, alert_status = self._alerts(lat, lon)
        retrieved = self._now() - (age or 0.0)
        return {
            "status": status, "error": error, "location_name": location_name or f"{lat:.5f}, {lon:.5f}",
            "latitude": lat, "longitude": lon, "timezone": raw.get("timezone", "UTC"),
            "elevation_m": _num(raw.get("elevation")), "current": current_result,
            "hourly_24h": hourly_result, "daily_7d": daily_result,
            "forecast_horizon_hours": len(hourly_result), "forecast_horizon_days": len(daily_result),
            "air_quality": self._air_quality(lat, lon), "alerts": alerts, "alerts_status": alert_status,
            "provider": WEATHER_PROVIDER, "provider_registry": self.provider_registry,
            "observation_time": observed or None, "retrieved_at": _iso(retrieved), "timestamp_utc": _iso(retrieved),
            "cache_age_seconds": round(age, 1) if age is not None else None,
            "cache_expires_at": _iso(retrieved + self.cache_ttl_seconds),
            "is_live": status in {STATUS_LIVE, STATUS_LIVE_FALLBACK},
            "is_cached": status in {STATUS_CACHED, STATUS_STALE_CACHED},
        }

    def _unavailable(self, lat: float, lon: float, name: str, unit: str, status: str, error: str) -> dict[str, Any]:
        current = {key: None for key in (
            "temperature", "feels_like", "humidity_pct", "pressure_hpa", "precipitation_mm", "rain_mm",
            "snowfall_cm", "wind_speed_kmh", "wind_direction_deg", "wind_gusts_kmh", "visibility_km",
            "cloud_cover_pct", "uv_index", "observation_time", "sunrise", "sunset",
        )}
        current.update({"unit": unit, "weather_condition": STATUS_DATA_UNAVAILABLE})
        now = _iso(self._now())
        return {
            "status": status or STATUS_DATA_UNAVAILABLE, "error": error or "No live or cached weather data is available.",
            "location_name": name, "latitude": lat, "longitude": lon, "timezone": None, "elevation_m": None,
            "current": current, "hourly_24h": [], "daily_7d": [], "forecast_horizon_hours": 0,
            "forecast_horizon_days": 0, "air_quality": {"available": False, "status": "Air Quality Data Unavailable",
                "aqi_category": "Air Quality Data Unavailable", "data_source": AIR_QUALITY_PROVIDER, "provenance": "Unavailable"},
            "alerts": [], "alerts_status": "Official Weather Alerts Unavailable", "provider": WEATHER_PROVIDER,
            "provider_registry": self.provider_registry, "observation_time": None, "retrieved_at": now,
            "timestamp_utc": now, "cache_age_seconds": None, "cache_expires_at": None,
            "is_live": False, "is_cached": False,
        }

    def load_saved_locations(self) -> list[dict[str, Any]]:
        if not self.location_store.is_file():
            return []
        try:
            data = json.loads(self.location_store.read_text(encoding="utf-8"))
            return [row for row in data.get("locations", []) if isinstance(row, dict)]
        except (OSError, json.JSONDecodeError):
            return []

    @property
    def saved_locations(self) -> list[dict[str, Any]]:
        return self.load_saved_locations()

    def save_location(self, location: dict[str, Any], *, location_type: str = "Research site") -> None:
        lat, lon = self._coords(location["latitude"], location["longitude"])
        key = f"{lat:.5f},{lon:.5f}"
        rows = [row for row in self.load_saved_locations() if row.get("key") != key]
        rows.append({
            "key": key, "name": str(location.get("name") or key), "latitude": lat, "longitude": lon,
            "country": str(location.get("country", "")), "admin1": str(location.get("admin1", "")),
            "timezone": str(location.get("timezone", "UTC")), "type": location_type, "saved_at": _iso(self._now()),
        })
        self.location_store.write_text(json.dumps({"locations": rows}, indent=2), encoding="utf-8")

    def remove_saved_location(self, key: str) -> bool:
        rows = self.load_saved_locations()
        kept = [row for row in rows if row.get("key") != key]
        if len(kept) == len(rows):
            return False
        self.location_store.write_text(json.dumps({"locations": kept}, indent=2), encoding="utf-8")
        return True

    def compare_multiple_locations(self, locations: list[dict[str, Any]] | None = None, *, unit_temp: str = "Celsius") -> list[dict[str, Any]]:
        result = []
        for location in locations or self.load_saved_locations():
            weather = self.fetch_weather_and_forecast(location["latitude"], location["longitude"], location.get("name", "Saved location"), unit_temp)
            current = weather["current"]
            result.append({"location": location.get("name"), "type": location.get("type", "Research site"),
                "status": weather["status"], "temperature": current.get("temperature"), "unit": current.get("unit"),
                "condition": current.get("weather_condition"), "humidity_pct": current.get("humidity_pct"),
                "wind_speed_kmh": current.get("wind_speed_kmh"), "air_quality": weather["air_quality"].get("aqi_category"),
                "retrieved_at": weather.get("retrieved_at")})
        return result

    def link_weather_to_project_provenance(self, project_id: str, sample_id: str, location_name: str, lat: float, lon: float) -> dict[str, Any]:
        weather = self.fetch_weather_and_forecast(lat, lon, location_name)
        return {"project_id": project_id, "sample_id": sample_id, "environmental_metadata": {
            "location_name": location_name, "latitude": lat, "longitude": lon, "current": weather["current"],
            "observation_time": weather.get("observation_time"), "retrieved_at": weather.get("retrieved_at"),
            "provider": weather["provider"], "delivery_state": weather["status"]},
            "status": "Environmental Metadata Recorded" if weather["is_live"] or weather["is_cached"] else STATUS_DATA_UNAVAILABLE}

    @staticmethod
    def _aqi_category(aqi: float | None) -> str:
        if aqi is None: return "Air Quality Data Unavailable"
        if aqi <= 50: return "Good"
        if aqi <= 100: return "Moderate"
        if aqi <= 150: return "Unhealthy for Sensitive Groups"
        if aqi <= 200: return "Unhealthy"
        if aqi <= 300: return "Very Unhealthy"
        return "Hazardous"

    @staticmethod
    def _wmo(code: Any) -> str:
        try:
            code = int(code)
        except (TypeError, ValueError):
            return "Condition Unavailable"
        return {0: "Clear Sky", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast", 45: "Fog",
            48: "Rime Fog", 51: "Light Drizzle", 53: "Moderate Drizzle", 55: "Dense Drizzle",
            61: "Slight Rain", 63: "Moderate Rain", 65: "Heavy Rain", 71: "Slight Snow",
            73: "Moderate Snow", 75: "Heavy Snow", 80: "Slight Rain Showers", 81: "Rain Showers",
            82: "Violent Rain Showers", 95: "Thunderstorm", 96: "Thunderstorm with Hail",
            99: "Thunderstorm with Heavy Hail"}.get(code, f"WMO code {code}")


__all__ = ["AIR_QUALITY_PROVIDER", "ProviderRequestError", "STATUS_AUTH_REQUIRED", "STATUS_CACHED",
    "STATUS_DATA_UNAVAILABLE", "STATUS_LIVE", "STATUS_LIVE_FALLBACK", "STATUS_LOCATION_NOT_FOUND",
    "STATUS_OFFLINE", "STATUS_PROVIDER_UNAVAILABLE", "STATUS_RATE_LIMITED", "STATUS_STALE_CACHED",
    "WeatherEnvironmentEngine"]