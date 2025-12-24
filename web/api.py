"""
StormWatch AI - FastAPI Backend
Serves REST API for weather, alerts, and chat
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import get_settings
from src.api.weather_client import WeatherClient
from src.rag.retriever import TemporalRetriever
from src.rag.generator import WeatherAdvisor

# Initialize app
app = FastAPI(title="StormWatch AI API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
settings = get_settings()

@app.get("/api/cities")
async def get_cities():
    """Get list of monitored cities from configuration."""
    cities = [c.strip() for c in settings.monitored_cities.split(",") if c.strip()]
    return {"cities": cities}

weather_client = WeatherClient(
    api_key=settings.openweathermap_api_key,
)

# Lazy load heavy services
_retriever = None
_advisor = None

def get_retriever():
    global _retriever
    if _retriever is None:
        _retriever = TemporalRetriever()
    return _retriever

def get_advisor():
    global _advisor
    if _advisor is None:
        _advisor = WeatherAdvisor()
    return _advisor


# ============ MODELS ============

class ChatRequest(BaseModel):
    message: str
    city: str = "Lyon"

class ChatResponse(BaseModel):
    response: str
    has_alerts: bool
    sources: List[Dict[str, Any]]

class WeatherResponse(BaseModel):
    temperature: float
    feels_like: float
    humidity: int
    wind_speed: float
    description: str
    city: str

# ============ ENDPOINTS ============

@app.get("/")
async def root():
    """Serve the main page."""
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api/weather/{city}")
async def get_weather(city: str):
    """Get current weather for a city from Qdrant (not API)."""
    try:
        retriever = get_retriever()
        
        # Get latest current_weather from Qdrant for this city
        results = retriever.retrieve_current_conditions(location=city)
        
        if results and len(results) > 0:
            # Get the most recent data
            raw_data = results[0].get("raw_data", {})
            return {
                "temperature": raw_data.get("temperature", 0),
                "feels_like": raw_data.get("feels_like", 0),
                "humidity": raw_data.get("humidity", 0),
                "wind_speed": raw_data.get("wind_speed", 0),
                "description": raw_data.get("weather", {}).get("description", "Unknown"),
                "city": city,
                "is_qdrant": True  # Data comes from Qdrant
            }
        else:
            # No data in Qdrant for this city
            return {
                "temperature": 0,
                "feels_like": 0,
                "humidity": 0,
                "wind_speed": 0,
                "description": "No data available",
                "city": city,
                "is_qdrant": True
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/air-quality/{city}")
async def get_air_quality(city: str):
    """Get latest air quality for a city from Qdrant."""
    try:
        retriever = get_retriever()
        
        # Use the same retriever method as the chat for consistency
        results = retriever.retrieve_air_quality(location=city)
        
        if results:
            raw_data = results[0].get("raw_data", {})
            return {
                "aqi": raw_data.get("aqi", 0),
                "aqi_label": raw_data.get("aqi_label", "Unknown"),
                "pm2_5": raw_data.get("components", {}).get("pm2_5", 0),
                "pm10": raw_data.get("components", {}).get("pm10", 0),
                "city": city,
                "timestamp": results[0].get("timestamp", "")
            }
        else:
            return {
                "aqi": 0,
                "aqi_label": "No data",
                "pm2_5": 0,
                "pm10": 0,
                "city": city,
                "timestamp": ""
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/alerts")
async def get_alerts(city: str = None):
    """Get active weather alerts, optionally filtered by city."""
    try:
        retriever = get_retriever()
        alerts = retriever.retrieve_alerts(top_k=5, location=city)
        
        return [{
            "event": a.get("raw_data", {}).get("event", "Alert"),
            "severity": a.get("raw_data", {}).get("severity", "Unknown"),
            "description": a.get("raw_data", {}).get("description", "")[:100],
            "location": a.get("raw_data", {}).get("location", "Unknown")
        } for a in alerts]
    except Exception as e:
        return []


@app.get("/api/stats")
async def get_stats():
    """Get system stats."""
    try:
        retriever = get_retriever()
        stats = retriever.get_collection_stats()
        return {
            "online": "error" not in stats,
            "vectors": stats.get("vectors_count", 0),
        }
    except Exception:
        return {"online": False, "vectors": 0}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Chat with the weather assistant."""
    try:
        advisor = get_advisor()
        result = advisor.generate_response(request.message, request.city)
        
        return {
            "response": result["response"],
            "has_alerts": result.get("has_alerts", False),
            "sources": result.get("sources", [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Mount static files
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
