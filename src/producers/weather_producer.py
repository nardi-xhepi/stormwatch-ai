"""Weather data Kafka producer."""

import json
import time
import logging
from datetime import datetime
from typing import List, Dict, Any
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from kafka import KafkaProducer
from kafka.errors import KafkaError
from config.settings import get_settings
from src.api.weather_client import WeatherClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class WeatherProducer:
    """Produces weather data to Kafka topics."""
    
    TOPIC_WEATHER = "weather-data"
    TOPIC_ALERTS = "weather-alerts"
    TOPIC_FORECAST = "weather-forecast"
    
    def __init__(self):
        self.settings = get_settings()
        self.weather_client = WeatherClient(
            api_key=self.settings.openweathermap_api_key,
        )
        
        # Initialize Kafka producer
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=self.settings.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks='all',
                retries=3
            )
            logger.info(f"Connected to Kafka at {self.settings.kafka_bootstrap_servers}")
        except KafkaError as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            raise
    
    def fetch_and_publish_unified(self, lat: float, lon: float, location_name: str = None) -> None:
        """Fetch all weather data in one call and publish to respective topics."""
        name = location_name or "Unknown"
        key = f"{lat:.4f}_{lon:.4f}"
        
        # 1. Try One Call API (3.0)
        one_call_data = self.weather_client.get_one_call(lat, lon)
        
        if one_call_data:
            # Publish Current Weather from One Call
            try:
                current_weather = self.weather_client.normalize_one_call_current(one_call_data, name)
                current_weather["ingestion_time"] = datetime.utcnow().isoformat()
                current_weather["data_type"] = "current_weather"
                
                self.producer.send(self.TOPIC_WEATHER, key=key, value=current_weather)
                logger.info(f"Published current weather for {name}")
            except Exception as e:
                logger.error(f"Failed to publish current weather for {name}: {e}")

            # Publish Forecast (Daily) - only if One Call succeeded
            try:
                forecast_data = self.weather_client.normalize_one_call_forecast(one_call_data, name)
                forecast_data["ingestion_time"] = datetime.utcnow().isoformat()
                forecast_data["data_type"] = "forecast"
                forecast_data["coordinates"] = {"lat": lat, "lon": lon}
                
                self.producer.send(self.TOPIC_FORECAST, key=key, value=forecast_data)
                logger.info(f"Published forecast for {name}")
            except Exception as e:
                logger.error(f"Failed to publish forecast for {name}: {e}")

            # Check and Publish Alerts - only if One Call succeeded
            alerts = one_call_data.get("alerts", [])
            if alerts:
                for alert in alerts:
                    try:
                        alert_data = self.weather_client.normalize_one_call_alert(alert, lat, lon, name)
                        alert_data["ingestion_time"] = datetime.utcnow().isoformat()
                        alert_data["data_type"] = "alert"
                        
                        alert_key = f"{lat:.4f}_{lon:.4f}_{alert_data['event'].replace(' ', '_')}_{alert.get('start')}"
                        
                        self.producer.send(self.TOPIC_ALERTS, key=alert_key, value=alert_data)
                        logger.warning(f"⚠️  Published alert for {name}: {alert_data['event']}")
                    except Exception as e:
                        logger.error(f"Failed to publish alert for {name}: {e}")
            else:
                logger.info(f"No active alerts for {name}")
        else:
            # Fallback to 2.5 API for current weather and forecast
            logger.warning(f"One Call failed for {name}, using 2.5 API fallback")
            try:
                current_weather = self.weather_client.get_current_weather(lat, lon)
                current_weather["location"] = name
                current_weather["ingestion_time"] = datetime.utcnow().isoformat()
                current_weather["data_type"] = "current_weather"
                
                self.producer.send(self.TOPIC_WEATHER, key=key, value=current_weather)
                logger.info(f"Published current weather (2.5 fallback) for {name}")
            except Exception as e:
                logger.error(f"Failed to publish weather fallback for {name}: {e}")
            
            # Fallback forecast from 2.5 API
            try:
                forecast_data = self.weather_client.get_forecast(lat, lon)
                forecast_data["location"] = name
                forecast_data["ingestion_time"] = datetime.utcnow().isoformat()
                forecast_data["data_type"] = "forecast"
                forecast_data["coordinates"] = {"lat": lat, "lon": lon}
                
                self.producer.send(self.TOPIC_FORECAST, key=key, value=forecast_data)
                logger.info(f"Published forecast (2.5 fallback) for {name}")
            except Exception as e:
                logger.error(f"Failed to publish forecast fallback for {name}: {e}")

    def publish_air_quality(self, lat: float, lon: float, location_name: str = None) -> Dict[str, Any]:
        """Fetch and publish air quality data (separate API call)."""
        aq_data = self.weather_client.get_air_quality(lat, lon)
        
        if location_name:
            aq_data["location"] = location_name
        
        aq_data["ingestion_time"] = datetime.utcnow().isoformat()
        aq_data["data_type"] = "air_quality"
        aq_data["coordinates"] = {"lat": lat, "lon": lon}
        
        key = f"{lat:.4f}_{lon:.4f}"
        
        try:
            future = self.producer.send(self.TOPIC_WEATHER, key=key, value=aq_data)
            future.get(timeout=10)
            logger.info(f"Published air quality for {location_name}: AQI {aq_data['aqi']} ({aq_data['aqi_label']})")
            return aq_data
        except KafkaError as e:
            logger.error(f"Failed to publish air quality: {e}")
            raise
    
    def run_continuous(self, locations: List[Dict[str, Any]] = None):
        """Run continuous weather data collection."""
        if locations is None:
            locations = [{
                "lat": self.settings.default_latitude,
                "lon": self.settings.default_longitude,
                "name": self.settings.default_city
            }]
        
        logger.info(f"Starting continuous weather producer for {len(locations)} location(s)")
        logger.info(f"Poll interval: {self.settings.weather_poll_interval} seconds")
        
        try:
            while True:
                for location in locations:
                    lat, lon = location["lat"], location["lon"]
                    name = location.get("name", "Unknown")
                    
                    logger.info(f"\n{'='*50}")
                    logger.info(f"Fetching weather data for {name} ({lat}, {lon})")
                    
                    # Unified Call (Current + Forecast + Alerts)
                    self.fetch_and_publish_unified(lat, lon, location_name=name)
                    
                    # Air quality (Separate)
                    self.publish_air_quality(lat, lon, location_name=name)


                
                logger.info(f"\nSleeping for {self.settings.weather_poll_interval} seconds...")
                time.sleep(self.settings.weather_poll_interval)
                
        except KeyboardInterrupt:
            logger.info("Shutting down producer...")
        finally:
            self.close()
    
    def close(self):
        """Close the Kafka producer."""
        if self.producer:
            self.producer.flush()
            self.producer.close()
            logger.info("Producer closed")


def main():
    """Main entry point for the weather producer."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Weather Data Kafka Producer")
    parser.add_argument("--test-mode", action="store_true", help="Run once and exit")
    parser.add_argument("--all-cities", action="store_true", help="Monitor all supported cities")
    args = parser.parse_args()
    
    producer = WeatherProducer()
    
    # Get cities from settings
    settings = get_settings()
    # Parse comma-separated list or fallback to list
    if hasattr(settings, "monitored_cities") and settings.monitored_cities:
         cities = [c.strip() for c in settings.monitored_cities.split(",") if c.strip()]
    else:
         cities = ["Lyon", "Paris", "Marseille", "Toulouse", "Nice"]
    
    if args.test_mode:
        logger.info("Running in test mode...")
        # Use first city or default
        test_city = cities[0] if cities else settings.default_city
        location = producer.weather_client.geocode(test_city)
        if location:
            producer.fetch_and_publish_unified(location["lat"], location["lon"], test_city)
            producer.publish_air_quality(location["lat"], location["lon"], test_city)
        else:
             logger.error(f"Could not geocode {test_city}")
        producer.close()
    else:
        # Collect locations for all cities
        locations = []
        for city in cities:
            location = producer.weather_client.geocode(city)
            if location:
                locations.append({
                    "lat": location["lat"],
                    "lon": location["lon"],
                    "name": city
                })
                logger.info(f"Added {city}: {location['lat']:.4f}, {location['lon']:.4f}")
        
        logger.info(f"Monitoring {len(locations)} cities: {cities}")
        producer.run_continuous(locations)


if __name__ == "__main__":
    main()
