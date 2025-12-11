"""Configuration settings for StormWatch AI."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # OpenWeatherMap
    openweathermap_api_key: str = ""
    
    # Gemini
    gemini_api_key: str = ""
    
    # Groq
    groq_api_key: str = ""
    
    # Kafka
    kafka_bootstrap_servers: str = "localhost:9093"
    
    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str = ""  # For cloud Qdrant
    
    # Default location
    default_latitude: float = 45.7640
    default_longitude: float = 4.8357
    default_city: str = "Lyon"
    
    monitored_cities: str = "Lyon,Paris,Marseille,Toulouse,Nice,Bordeaux,Strasbourg,Rouen"
    
    # Polling
    weather_poll_interval: int = 120
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra fields in .env


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
