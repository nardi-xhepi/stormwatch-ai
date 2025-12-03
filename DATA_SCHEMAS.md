# Data Schemas

This document describes the structure of data flowing through each Kafka topic in StormWatch AI.

---

## Kafka Topics

| Topic | Description |
|-------|-------------|
| `weather-data` | Current weather conditions and air quality |
| `weather-alerts` | Weather alerts (mock generation enabled) |
| `weather-forecast` | 5-day/3-hour forecasts |

---

## Data Type: `current_weather`

**Topic:** `weather-data`

```json
{
  "timestamp": "2025-12-26T15:32:36.123456",
  "location": "Lyon",
  "coordinates": {
    "lat": 45.7578,
    "lon": 4.8320
  },
  "temperature": 1.18,
  "feels_like": -1.69,
  "humidity": 93,
  "pressure": 1019,
  "wind_speed": 2.57,
  "wind_direction": 319,
  "clouds": 75,
  "visibility": 10000,
  "weather": {
    "main": "Clouds",
    "description": "overcast clouds",
    "icon": "04d"
  },
  "source": "openweathermap",
  "ingestion_time": "2025-12-26T15:32:36.123456",
  "data_type": "current_weather"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string (ISO 8601) | Time of observation |
| `location` | string | City name |
| `coordinates` | object | Latitude and longitude |
| `temperature` | float | Temperature in Celsius |
| `feels_like` | float | Perceived temperature in Celsius |
| `humidity` | int | Humidity percentage (0-100) |
| `pressure` | int | Atmospheric pressure in hPa |
| `wind_speed` | float | Wind speed in m/s |
| `wind_direction` | int | Wind direction in degrees |
| `clouds` | int | Cloud coverage percentage |
| `visibility` | int | Visibility in meters |
| `weather.main` | string | Weather condition group |
| `weather.description` | string | Detailed description |
| `weather.icon` | string | OpenWeatherMap icon code |
| `source` | string | Data source identifier |
| `ingestion_time` | string (ISO 8601) | When data was ingested |
| `data_type` | string | Always "current_weather" |

---

## Data Type: `air_quality`

**Topic:** `weather-data`

```json
{
  "timestamp": "2025-12-26T15:32:36.123456",
  "location": "Lyon",
  "aqi": 2,
  "aqi_label": "Fair",
  "components": {
    "co": 230.31,
    "no": 0.15,
    "no2": 7.84,
    "o3": 68.78,
    "so2": 1.64,
    "pm2_5": 5.42,
    "pm10": 8.13,
    "nh3": 0.67
  },
  "source": "openweathermap",
  "ingestion_time": "2025-12-26T15:32:36.123456",
  "data_type": "air_quality"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string (ISO 8601) | Time of observation |
| `location` | string | City name |
| `aqi` | int | Air Quality Index (1-5) |
| `aqi_label` | string | Human-readable AQI label |
| `components` | object | Pollutant concentrations (μg/m³) |
| `source` | string | Data source identifier |
| `data_type` | string | Always "air_quality" |

**AQI Scale:**
| Value | Label |
|-------|-------|
| 1 | Good |
| 2 | Fair |
| 3 | Moderate |
| 4 | Poor |
| 5 | Very Poor |

---

## Data Type: `forecast`

**Topic:** `weather-forecast`

```json
{
  "timestamp": "2025-12-26T15:32:36.123456",
  "location": "Lyon",
  "forecasts": [
    {
      "timestamp": "2025-12-26 18:00:00",
      "temperature": 2.5,
      "feels_like": -0.3,
      "humidity": 85,
      "wind_speed": 3.1,
      "clouds": 100,
      "weather": {
        "main": "Clouds",
        "description": "overcast clouds"
      },
      "pop": 0
    },
    {
      "timestamp": "2025-12-26 21:00:00",
      "temperature": 1.8,
      "feels_like": -1.2,
      "humidity": 88,
      "wind_speed": 2.8,
      "clouds": 95,
      "weather": {
        "main": "Clouds",
        "description": "broken clouds"
      },
      "pop": 10
    }
  ],
  "source": "openweathermap",
  "ingestion_time": "2025-12-26T15:32:36.123456",
  "data_type": "forecast"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string (ISO 8601) | When forecast was generated |
| `location` | string | City name |
| `forecasts` | array | List of forecast entries (up to 40) |
| `forecasts[].timestamp` | string | Forecast time |
| `forecasts[].temperature` | float | Predicted temperature (°C) |
| `forecasts[].feels_like` | float | Predicted feels-like (°C) |
| `forecasts[].humidity` | int | Predicted humidity (%) |
| `forecasts[].wind_speed` | float | Predicted wind speed (m/s) |
| `forecasts[].clouds` | int | Predicted cloud coverage (%) |
| `forecasts[].pop` | int | Probability of precipitation (0-100%) |
| `source` | string | Data source identifier |
| `data_type` | string | Always "forecast" |

---

## Data Type: `alert`

**Topic:** `weather-alerts`

> **Note:** Alerts are generated using mock data with a 20% probability each polling cycle.

```json
{
  "timestamp": "2025-12-26T15:32:36.123456",
  "location": "Lyon",
  "event": "Thunderstorm Warning",
  "sender": "National Weather Service",
  "severity": "Moderate",
  "certainty": "Likely",
  "urgency": "Expected",
  "description": "Thunderstorms expected in the area...",
  "start": "2025-12-26T18:00:00",
  "end": "2025-12-26T23:00:00",
  "source": "openweathermap",
  "data_type": "alert"
}
```

---

## Qdrant Vector Storage

All data types are stored in the `weather_data` collection with these payload fields:

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | Human-readable text representation |
| `data_type` | string | Type identifier for filtering |
| `timestamp` | string | ISO 8601 timestamp |
| `location` | string | City name |
| `raw_data` | object | Original data structure |

**Indexes:** Keyword indexes on `location` and `data_type` for efficient filtering.
