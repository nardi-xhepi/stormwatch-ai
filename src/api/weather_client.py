"""OpenWeatherMap API Client"""

import requests
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class WeatherClient:
    """Client for OpenWeatherMap API"""
    
    BASE_URL = "https://api.openweathermap.org/data/2.5"
    GEO_URL = "https://api.openweathermap.org/geo/1.0"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        
    def _make_request(self, url: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Make API request with error handling."""
        params["appid"] = self.api_key
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"API error {response.status_code}: {response.text}")
                return None
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            return None

    def get_one_call(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Get comprehensive weather data using One Call API 3.0."""
        url = "https://api.openweathermap.org/data/3.0/onecall"
        params = {
            "lat": lat, 
            "lon": lon, 
            "units": "metric",
            "exclude": "minutely,hourly"
        }
        return self._make_request(url, params)

    def get_current_weather(self, lat: float, lon: float) -> Dict[str, Any]:
        """Get current weather (Legacy/Fallback)."""
        url = f"{self.BASE_URL}/weather"
        data = self._make_request(url, {"lat": lat, "lon": lon, "units": "metric"})
        if data:
            return self._normalize_current(data)
            
    def get_forecast(self, lat: float, lon: float) -> Dict[str, Any]:
        """Get 5-day/3-hour forecast."""
        url = f"{self.BASE_URL}/forecast"
        data = self._make_request(url, {"lat": lat, "lon": lon, "units": "metric"})
        if data:
            return self._normalize_forecast(data)

    def get_air_quality(self, lat: float, lon: float) -> Dict[str, Any]:
        """Get current air quality data."""
        url = f"{self.BASE_URL}/air_pollution"
        data = self._make_request(url, {"lat": lat, "lon": lon})
        if data:
            return self._normalize_air_quality(data)
            
    def geocode(self, city: str, country: str = "FR") -> Optional[Dict[str, Any]]:
        """Get coordinates for a city name."""
        url = f"{self.GEO_URL}/direct"
        data = self._make_request(url, {"q": f"{city},{country}", "limit": 1})
        if data and len(data) > 0:
            return {"lat": data[0]["lat"], "lon": data[0]["lon"], "name": data[0]["name"]}

    # ========== NORMALIZATION METHODS ==========

    def normalize_one_call_current(self, data: Dict[str, Any], location_name: str) -> Dict[str, Any]:
        """Normalize One Call 'current' data to our schema."""
        current = data.get("current", {})
        return {
            "timestamp": datetime.fromtimestamp(current.get("dt", 0)).replace(microsecond=0).isoformat(),
            "location": location_name,
            "coordinates": {"lat": data.get("lat"), "lon": data.get("lon")},
            "temperature": current.get("temp"),
            "feels_like": current.get("feels_like"),
            "humidity": current.get("humidity"),
            "pressure": current.get("pressure"),
            "wind_speed": current.get("wind_speed"),
            "wind_direction": current.get("wind_deg", 0),
            "clouds": current.get("clouds"),
            "visibility": current.get("visibility", 10000),
            "weather": {
                "main": current["weather"][0]["main"] if current.get("weather") else "Unknown",
                "description": current["weather"][0]["description"] if current.get("weather") else "Unknown",
                "icon": current["weather"][0]["icon"] if current.get("weather") else "01d"
            },
            "source": "openweathermap_onecall"
        }

    def normalize_one_call_forecast(self, data: Dict[str, Any], location_name: str) -> Dict[str, Any]:
        """Normalize One Call 'daily' data to our forecast schema."""
        daily_items = data.get("daily", [])
        forecasts = []
        for item in daily_items:
            forecasts.append({
                "timestamp": datetime.fromtimestamp(item.get("dt", 0)).isoformat(),
                "temperature": item.get("temp", {}).get("day"), # Use day temp as reference
                "feels_like": item.get("feels_like", {}).get("day"),
                "humidity": item.get("humidity"),
                "wind_speed": item.get("wind_speed"),
                "clouds": item.get("clouds"),
                "weather": {
                    "main": item["weather"][0]["main"] if item.get("weather") else "Unknown",
                    "description": item["weather"][0]["description"] if item.get("weather") else "Unknown"
                },
                "pop": item.get("pop", 0) * 100,
                "summary": item.get("summary", "") # One Call 3.0 provides a text summary
            })
        
        return {
            "location": location_name,
            "forecasts": forecasts,
            "source": "openweathermap_onecall"
        }

    def normalize_one_call_alert(self, alert_data: Dict[str, Any], lat: float, lon: float, location_name: str) -> Dict[str, Any]:
        """Normalize One Call alert to our schema."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "coordinates": {"lat": lat, "lon": lon},
            "location": location_name,
            "event": alert_data.get("event", "Unknown Alert"),
            "severity": "Unknown", # OWM 3.0 usually doesn't give severity level directly, inferred or generic
            "sender": alert_data.get("sender_name", "OpenWeatherMap"),
            "description": alert_data.get("description", ""),
            "urgency": "Unknown",
            "tags": alert_data.get("tags", []),
            "start": datetime.fromtimestamp(alert_data.get("start", 0)).isoformat(),
            "end": datetime.fromtimestamp(alert_data.get("end", 0)).isoformat(),
            "source": "openweathermap_onecall"
        }
    
    def _normalize_current(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize current weather response."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "location": data.get("name", "Unknown"),
            "coordinates": {"lat": data["coord"]["lat"], "lon": data["coord"]["lon"]},
            "temperature": data["main"]["temp"],
            "feels_like": data["main"]["feels_like"],
            "humidity": data["main"]["humidity"],
            "pressure": data["main"]["pressure"],
            "wind_speed": data["wind"]["speed"],
            "wind_direction": data["wind"].get("deg", 0),
            "clouds": data["clouds"]["all"],
            "visibility": data.get("visibility", 10000),
            "weather": {
                "main": data["weather"][0]["main"],
                "description": data["weather"][0]["description"],
                "icon": data["weather"][0]["icon"]
            },
            "source": "openweathermap"
        }
    
    def _normalize_forecast(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize forecast response."""
        forecasts = []
        for item in data["list"]:
            forecasts.append({
                "timestamp": item["dt_txt"],
                "temperature": item["main"]["temp"],
                "feels_like": item["main"]["feels_like"],
                "humidity": item["main"]["humidity"],
                "wind_speed": item["wind"]["speed"],
                "clouds": item["clouds"]["all"],
                "weather": {
                    "main": item["weather"][0]["main"],
                    "description": item["weather"][0]["description"]
                },
                "pop": item.get("pop", 0) * 100  # Probability of precipitation
            })
        
        return {
            "location": data["city"]["name"],
            "forecasts": forecasts,
            "source": "openweathermap"
        }
    
    def _normalize_air_quality(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize air quality response."""
        aqi_labels = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very Poor"}
        aqi = data["list"][0]["main"]["aqi"]
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "aqi": aqi,
            "aqi_label": aqi_labels.get(aqi, "Unknown"),
            "components": data["list"][0]["components"],
            "source": "openweathermap"
        }