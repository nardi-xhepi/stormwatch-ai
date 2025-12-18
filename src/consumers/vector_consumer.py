"""Vector consumer - consumes Kafka messages and stores embeddings in Qdrant."""

import json
import logging
from datetime import datetime
from typing import Dict, Any, List
import sys
import os
import uuid

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from kafka import KafkaConsumer
from kafka.errors import KafkaError
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct, 
    PayloadSchemaType, TextIndexParams, TokenizerType
)

from config.settings import get_settings
from src.rag.embeddings import EmbeddingModel

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class VectorConsumer:
    """Consumes weather data from Kafka and stores vectors in Qdrant."""
    
    COLLECTION_NAME = "weather_data"
    
    def __init__(self):
        self.settings = get_settings()
        self.embedding_model = EmbeddingModel()
        
        # Initialize Qdrant client (supports both local and cloud)
        if self.settings.qdrant_api_key:
            # Cloud Qdrant
            self.qdrant = QdrantClient(
                url=self.settings.qdrant_host,
                api_key=self.settings.qdrant_api_key
            )
        else:
            # Local Qdrant
            self.qdrant = QdrantClient(
                host=self.settings.qdrant_host,
                port=self.settings.qdrant_port
            )
        
        # Ensure collection exists
        self._init_collection()
        
        # Initialize Kafka consumer
        self.consumer = KafkaConsumer(
            "weather-data",
            "weather-alerts",
            "weather-forecast",
            "weather-news",
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            group_id="vector-consumer-group",
            auto_offset_reset="earliest",
            enable_auto_commit=True
        )
        
        logger.info("Vector consumer initialized")
    
    def _init_collection(self):
        """Initialize Qdrant collection if it doesn't exist."""
        try:
            collections = self.qdrant.get_collections().collections
            if not any(c.name == self.COLLECTION_NAME for c in collections):
                self.qdrant.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self.embedding_model.dimension,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created collection '{self.COLLECTION_NAME}'")
                
                # Create payload index for efficient filtering
                self.qdrant.create_payload_index(
                    collection_name=self.COLLECTION_NAME,
                    field_name="data_type",
                    field_schema=PayloadSchemaType.KEYWORD
                )
                self.qdrant.create_payload_index(
                    collection_name=self.COLLECTION_NAME,
                    field_name="timestamp",
                    field_schema=PayloadSchemaType.DATETIME
                )
            else:
                logger.info(f"Collection '{self.COLLECTION_NAME}' already exists")
        except Exception as e:
            logger.error(f"Failed to initialize collection: {e}")
            raise
    
    def _create_text_representation(self, data: Dict[str, Any]) -> str:
        """Create a text representation of weather data for embedding."""
        data_type = data.get("data_type", "unknown")
        
        if data_type == "current_weather":
            weather = data.get("weather", {})
            return (
                f"Current weather conditions: {weather.get('description', 'unknown')}. "
                f"Temperature is {data.get('temperature', 'N/A')}°C, "
                f"feels like {data.get('feels_like', 'N/A')}°C. "
                f"Humidity at {data.get('humidity', 'N/A')}%, "
                f"wind speed {data.get('wind_speed', 'N/A')} m/s. "
                f"Visibility {data.get('visibility', 'N/A')} meters. "
                f"Location: {data.get('location', 'Unknown')}."
            )
        
        elif data_type == "alert":
            return (
                f"WEATHER ALERT: {data.get('event', 'Unknown alert')}. "
                f"Severity: {data.get('severity', 'Unknown')}. "
                f"Urgency: {data.get('urgency', 'Unknown')}. "
                f"{data.get('description', '')} "
                f"Valid from {data.get('start', 'now')} to {data.get('end', 'unknown')}."
            )
        
        elif data_type == "forecast":
            # Create summary of the forecast
            forecasts = data.get("forecasts", [])[:8]  # Next 24 hours (8 x 3-hour slots)
            if not forecasts:
                return "Forecast data unavailable."
            
            summary_parts = [f"Weather forecast for {data.get('location', 'location')}:"]
            for fc in forecasts[:4]:  # First 12 hours
                summary_parts.append(
                    f"At {fc.get('timestamp', 'N/A')}: {fc.get('weather', {}).get('description', 'N/A')}, "
                    f"{fc.get('temperature', 'N/A')}°C, {fc.get('pop', 0)}% precipitation chance."
                )
            return " ".join(summary_parts)
        
        elif data_type == "air_quality":
            return (
                f"Air quality index: {data.get('aqi', 'N/A')} ({data.get('aqi_label', 'Unknown')}). "
                f"PM2.5: {data.get('components', {}).get('pm2_5', 'N/A')} µg/m³, "
                f"PM10: {data.get('components', {}).get('pm10', 'N/A')} µg/m³."
            )
        
        elif data_type == "news":
            # Extract clean text from news articles for embedding
            title = data.get("title", "")
            description = data.get("description", "")
            # Use the pre-formatted text field if available, otherwise compose from title+description
            return data.get("text", f"{title}. {description}")
        
        else:
            return json.dumps(data)
    
    def process_message(self, message) -> bool:
        """Process a single Kafka message and store in Qdrant."""
        try:
            data = message.value
            topic = message.topic
            
            # Create text representation
            text = self._create_text_representation(data)
            
            # Generate embedding
            embedding = self.embedding_model.embed(text)
            
            # Deterministic ID for alerts (to prevent duplicates), random for others
            if data.get("data_type") == "alert":
                # Hash of event + location + start + end = same alert gets same ID
                import hashlib
                unique_str = f"{data.get('event', '')}{data.get('location', '')}{data.get('start', '')}{data.get('end', '')}"
                point_id = hashlib.md5(unique_str.encode()).hexdigest()
            else:
                point_id = str(uuid.uuid4())
            
            # Prepare payload
            payload = {
                "text": text,
                "data_type": data.get("data_type", "unknown"),
                "timestamp": data.get("timestamp") or data.get("ingestion_time") or datetime.utcnow().isoformat(),
                "ingestion_time": data.get("ingestion_time", datetime.utcnow().isoformat()),
                "topic": topic,
                "raw_data": data
            }
            
            # Add location and coordinates if available
            if "location" in data:
                payload["location"] = data["location"]
            if "coordinates" in data:
                payload["lat"] = data["coordinates"]["lat"]
                payload["lon"] = data["coordinates"]["lon"]
            
            # Add alert-specific fields
            if data.get("data_type") == "alert":
                payload["event"] = data.get("event")
                payload["severity"] = data.get("severity")
                payload["urgency"] = data.get("urgency")
            
            # Store in Qdrant
            self.qdrant.upsert(
                collection_name=self.COLLECTION_NAME,
                points=[PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload
                )]
            )
            
            logger.info(f"Stored vector for {data.get('data_type', 'unknown')} data (topic: {topic})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to process message: {e}")
            return False
    
    def run(self):
        """Run the consumer loop."""
        logger.info("Starting vector consumer...")
        
        try:
            for message in self.consumer:
                self.process_message(message)
        except KeyboardInterrupt:
            logger.info("Shutting down consumer...")
        finally:
            self.close()
    
    def close(self):
        """Close connections."""
        if self.consumer:
            self.consumer.close()
        logger.info("Consumer closed")


def main():
    """Main entry point."""
    consumer = VectorConsumer()
    consumer.run()


if __name__ == "__main__":
    main()
