"""OpenWeatherMap API Client with mock data fallback."""

import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import random
import math
import logging

logger = logging.getLogger(__name__)


class WeatherClient:
    """Client for OpenWeatherMap API with mock data support."""
    
    BASE_URL = "https://api.openweathermap.org/data/2.5"
    GEO_URL = "https://api.openweathermap.org/geo/1.0"
    
    def __init__(self, api_key: str, use_mock: bool = False):
        self.api_key = api_key
        self.use_mock = use_mock
        
    def _make_request(self, url: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Make API request with error handling."""
        params["appid"] = self.api_key
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                logger.warning("API key not activated yet, using mock data")
                self.use_mock = True
                return None
            else:
                logger.error(f"API error {response.status_code}: {response.text}")
                return None
        except requests.RequestException as e:
            logger.error(f"Request failed: {e}")
            return None

    def get_one_call(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Get comprehensive weather data using One Call API 3.0."""
        if not self.use_mock:
            # Note: One Call 3.0 is a different base URL than 2.5
            url = "https://api.openweathermap.org/data/3.0/onecall"
            params = {
                "lat": lat, 
                "lon": lon, 
                "units": "metric",
                "exclude": "minutely,hourly"  # Keep current, daily (forecast), and alerts
            }
            return self._make_request(url, params)
        
        # Mock fallback for One Call
        return {
            "current": self._generate_mock_current_raw(lat, lon),
            "daily": self._generate_mock_daily_raw(),
            "alerts": [self._generate_mock_alert_raw(lat, lon)] if random.random() < 0.8 else []
        }
    
    def get_current_weather(self, lat: float, lon: float) -> Dict[str, Any]:
        """Get current weather (Legacy/Fallback)."""
        if not self.use_mock:
            url = f"{self.BASE_URL}/weather"
            data = self._make_request(url, {"lat": lat, "lon": lon, "units": "metric"})
            if data:
                return self._normalize_current(data)
        
        return self._generate_mock_current(lat, lon)
    
    def get_forecast(self, lat: float, lon: float) -> Dict[str, Any]:
        """Get 5-day/3-hour forecast."""
        if not self.use_mock:
            url = f"{self.BASE_URL}/forecast"
            data = self._make_request(url, {"lat": lat, "lon": lon, "units": "metric"})
            if data:
                return self._normalize_forecast(data)
        
        return self._generate_mock_forecast(lat, lon)
    
    def get_air_quality(self, lat: float, lon: float) -> Dict[str, Any]:
        """Get current air quality data."""
        if not self.use_mock:
            url = f"{self.BASE_URL}/air_pollution"
            data = self._make_request(url, {"lat": lat, "lon": lon})
            if data:
                return self._normalize_air_quality(data)
        
        return self._generate_mock_air_quality(lat, lon)
    
    def geocode(self, city: str, country: str = "FR") -> Optional[Dict[str, Any]]:
        """Get coordinates for a city name."""
        if not self.use_mock:
            url = f"{self.GEO_URL}/direct"
            data = self._make_request(url, {"q": f"{city},{country}", "limit": 1})
            if data and len(data) > 0:
                return {"lat": data[0]["lat"], "lon": data[0]["lon"], "name": data[0]["name"]}
        
        # Mock geocoding for common French cities
        cities = {
            "paris": {"lat": 48.8566, "lon": 2.3522, "name": "Paris"},
            "lyon": {"lat": 45.7640, "lon": 4.8357, "name": "Lyon"},
            "marseille": {"lat": 43.2965, "lon": 5.3698, "name": "Marseille"},
            "toulouse": {"lat": 43.6047, "lon": 1.4442, "name": "Toulouse"},
            "nice": {"lat": 43.7102, "lon": 7.2620, "name": "Nice"},
            "nantes": {"lat": 47.2184, "lon": -1.5536, "name": "Nantes"},
            "bordeaux": {"lat": 44.8378, "lon": -0.5792, "name": "Bordeaux"},
        }
        return cities.get(city.lower(), cities["lyon"])

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
    
    # ========== MOCK DATA GENERATION ==========
    
    def _generate_mock_current(self, lat: float, lon: float) -> Dict[str, Any]:
        """Generate realistic mock current weather."""
        data = self._generate_mock_current_raw(lat, lon, format="legacy")
        return self._normalize_current(data)

    def _generate_mock_current_raw(self, lat: float, lon: float, format="onecall") -> Dict[str, Any]:
        # Seasonal temperature variation
        month = datetime.now().month
        base_temp = 10 + 10 * math.sin((month - 4) * math.pi / 6)  # Peak in July
        temp = base_temp + random.uniform(-3, 3)
        
        # Weather conditions
        conditions = [
            ("Clear", "clear sky", "01d"),
            ("Clouds", "few clouds", "02d"),
            ("Rain", "light rain", "10d"),
        ]
        weather = random.choice(conditions)
        
        if format == "legacy":
            return {
                "name": "Mock Location",
                "coord": {"lat": lat, "lon": lon},
                "main": {
                    "temp": round(temp, 1),
                    "feels_like": round(temp - 2, 1),
                    "humidity": random.randint(40, 90),
                    "pressure": 1013
                },
                "wind": {"speed": 5.0, "deg": 180},
                "clouds": {"all": 20},
                "weather": [{"main": weather[0], "description": weather[1], "icon": weather[2]}]
            }
        else:
            return {
                "dt": int(datetime.utcnow().timestamp()),
                "sunrise": int(datetime.utcnow().timestamp()) - 10000,
                "sunset": int(datetime.utcnow().timestamp()) + 10000,
                "temp": round(temp, 1),
                "feels_like": round(temp - 2, 1),
                "pressure": 1013,
                "humidity": random.randint(40, 90),
                "dew_point": 10.0,
                "uvi": 5.0,
                "clouds": 20,
                "visibility": 10000,
                "wind_speed": 5.0,
                "wind_deg": 180,
                "weather": [{"id": 800, "main": weather[0], "description": weather[1], "icon": weather[2]}]
            }

    def _generate_mock_forecast(self, lat: float, lon: float) -> Dict[str, Any]:
        """Generate mock 5-day forecast."""
        # Simple implementation for legacy mock
        return {
            "city": {"name": "Mock Location"},
            "list": [
                {
                    "dt_txt": (datetime.utcnow() + timedelta(hours=i*3)).strftime("%Y-%m-%d %H:%M:%S"),
                    "main": {"temp": 20.0, "feels_like": 18.0, "humidity": 60},
                    "wind": {"speed": 5.0},
                    "clouds": {"all": 20},
                    "weather": [{"main": "Clear", "description": "clear sky"}]
                } for i in range(40)
            ],
            "source": "mock"
        }

    def _generate_mock_daily_raw(self) -> List[Dict[str, Any]]:
        return [
            {
                "dt": int((datetime.utcnow() + timedelta(days=i)).timestamp()),
                "temp": {"day": 20.0, "min": 15.0, "max": 25.0, "night": 18.0, "eve": 22.0, "morn": 16.0},
                "feels_like": {"day": 18.0, "night": 16.0, "eve": 20.0, "morn": 15.0},
                "pressure": 1013,
                "humidity": 60,
                "weather": [{"id": 800, "main": "Clear", "description": "clear sky", "icon": "01d"}],
                "clouds": 0,
                "pop": 0.0,
                "uvi": 5.0
            } for i in range(7)
        ]

    def _generate_mock_air_quality(self, lat: float, lon: float) -> Dict[str, Any]:
        """Generate mock air quality data."""
        aqi = random.choices([1, 2, 3, 4, 5], weights=[0.4, 0.3, 0.2, 0.08, 0.02])[0]
        aqi_labels = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very Poor"}
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "aqi": aqi,
            "aqi_label": aqi_labels[aqi],
            "components": {
                "co": random.uniform(200, 400),
                "no2": random.uniform(10, 50),
                "o3": random.uniform(40, 100),
                "pm2_5": random.uniform(5, 25),
                "pm10": random.uniform(10, 40)
            },
            "source": "mock"
        }
    
    def generate_mock_alert(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Generate mock weather alert (legacy wrapper)."""
        raw = self._generate_mock_alert_raw(lat, lon)
        if raw:
            return self.normalize_one_call_alert(raw, lat, lon, "Mock Location")
        return None

    def _generate_mock_alert_raw(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Generate mock weather alert raw data."""
        """Generate mock weather alert raw data."""
        # Random check removed, controlled by caller
        
        alert_types = [
            ("Thunderstorm Warning", "Moderate", "Thunderstorms expected."),
            ("Heavy Rain Advisory", "Minor", "Heavy rainfall expected."),
            ("Wind Advisory", "Moderate", "Strong winds expected."),
            ("Heat Wave Warning", "Severe", "Extreme heat expected."),
            ("Flash Flood Warning", "Severe", "Flash flooding possible."),
        ]
        
        alert = random.choice(alert_types)
        start = datetime.utcnow()
        end = start + timedelta(hours=random.randint(2, 12))
        
        return {
            "sender_name": "Mock Agency",
            "event": alert[0],
            "start": int(start.timestamp()),
            "end": int(end.timestamp()),
            "description": alert[2],
            "tags": [alert[1]]
        }
