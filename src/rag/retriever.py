"""Temporal-aware retriever for weather data from Qdrant."""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import math
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range

from config.settings import get_settings
from src.rag.embeddings import EmbeddingModel

logger = logging.getLogger(__name__)


class TemporalRetriever:
    """Retrieves weather data with temporal weighting for recency."""
    
    COLLECTION_NAME = "weather_data"
    
    # Decay parameters - how fast relevance drops with age
    DECAY_RATE = 0.1  # Higher = faster decay
    ALERT_BOOST = 2.0  # Boost factor for alerts
    
    def __init__(self):
        self.settings = get_settings()
        
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
        
        self.embedding_model = EmbeddingModel()
        logger.info("Temporal retriever initialized")
    
    def _calculate_time_decay(self, timestamp_str: str, max_age_minutes: int = 60) -> float:
        """Calculate decay factor based on age of data.
        
        Returns a value between 0 and 1, where:
        - 1.0 = just now (freshest)
        - approaches 0 = old data
        """
        try:
            # Parse timestamp
            if 'T' in timestamp_str:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            
            # Calculate age in minutes
            now = datetime.utcnow()
            if timestamp.tzinfo:
                now = now.replace(tzinfo=timestamp.tzinfo)
            
            age_minutes = (now - timestamp).total_seconds() / 60
            
            # Return 0 for data older than max_age (hard filter)
            if age_minutes > max_age_minutes:
                return 0.0
            
            # Exponential decay for recent data
            decay = math.exp(-self.DECAY_RATE * age_minutes / max_age_minutes)
            return min(1.0, decay)
            
        except Exception as e:
            logger.warning(f"Could not parse timestamp '{timestamp_str}': {e}")
            return 0.5  # Default middle value
    
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        data_types: Optional[List[str]] = None,
        max_age_minutes: int = 5,
        apply_temporal_weighting: bool = True,
        location: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant weather data with temporal weighting.
        
        Args:
            query: User query
            top_k: Number of results to return
            data_types: Filter by data types (e.g., ["current_weather", "alert"])
            max_age_minutes: Maximum age of data to consider
            apply_temporal_weighting: Whether to re-rank by recency
            location: Filter by location/city name
            
        Returns:
            List of relevant documents with scores
        """
        query_embedding = self.embedding_model.embed(query)
        
        filter_conditions = []
        
        if data_types:
            filter_conditions.append(
                FieldCondition(
                    key="data_type",
                    match=MatchValue(value=data_types[0]) if len(data_types) == 1 else None
                )
            )
        
        # Add location filter if specified
        if location:
            filter_conditions.append(
                FieldCondition(
                    key="location",
                    match=MatchValue(value=location)
                )
            )
        
        try:
            search_limit = top_k * 100 if apply_temporal_weighting else top_k
            
            # Use query_points for newer qdrant-client versions
            from qdrant_client.models import QueryRequest
            results = self.qdrant.query_points(
                collection_name=self.COLLECTION_NAME,
                query=query_embedding,
                limit=search_limit,
                with_payload=True,
                query_filter=Filter(must=filter_conditions) if filter_conditions else None
            ).points
            
            if not results:
                logger.info("No results found in Qdrant")
                return []
            
            # Process results
            documents = []
            for result in results:
                payload = result.payload
                
                timestamp = payload.get("timestamp") or payload.get("ingestion_time", "")
                time_decay = self._calculate_time_decay(timestamp, max_age_minutes)
                similarity_score = result.score
                
                if apply_temporal_weighting:
                    final_score = similarity_score * time_decay
                    if payload.get("data_type") == "alert":
                        final_score *= self.ALERT_BOOST
                else:
                    final_score = similarity_score
                
                documents.append({
                    "id": str(result.id),
                    "text": payload.get("text", ""),
                    "data_type": payload.get("data_type", "unknown"),
                    "timestamp": timestamp,
                    "location": payload.get("location", "Unknown"),
                    "raw_data": payload.get("raw_data", {}),
                    "similarity_score": similarity_score,
                    "time_decay": time_decay,
                    "final_score": final_score,
                    "source": payload.get("raw_data", {}).get("source", "unknown")
                })
            
            # Re-rank by final score
            documents.sort(key=lambda x: x["final_score"], reverse=True)
            
            # Filter out zero-score results (data too old)
            documents = [d for d in documents if d["final_score"] > 0]
            
            # Return top-k
            return documents[:top_k]
            
        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            return []
    
    def retrieve_alerts(self, top_k: int = 3, location: str = None) -> List[Dict[str, Any]]:
        """Retrieve currently valid weather alerts based on start/end times."""
        try:
            filter_conditions = [
                FieldCondition(key="data_type", match=MatchValue(value="alert"))
            ]
            if location:
                filter_conditions.append(
                    FieldCondition(key="location", match=MatchValue(value=location))
                )
            
            results = self.qdrant.scroll(
                collection_name=self.COLLECTION_NAME,
                scroll_filter=Filter(must=filter_conditions),
                limit=50,
                with_payload=True
            )[0]
            
            now = datetime.utcnow()
            documents = []
            
            for point in results:
                payload = point.payload
                raw_data = payload.get("raw_data", {})
                
                start_str = raw_data.get("start", "")
                end_str = raw_data.get("end", "")
                
                try:
                    start_time = datetime.fromisoformat(start_str.replace('Z', '+00:00')).replace(tzinfo=None) if start_str else None
                    end_time = datetime.fromisoformat(end_str.replace('Z', '+00:00')).replace(tzinfo=None) if end_str else None
                    
                    # Check if alert is currently valid (now between start and end)
                    if start_time and end_time and start_time <= now <= end_time:
                        documents.append({
                            "id": str(point.id),
                            "text": payload.get("text", ""),
                            "data_type": payload.get("data_type"),
                            "timestamp": payload.get("timestamp", ""),
                            "start": start_str,
                            "end": end_str,
                            "raw_data": payload,
                            "final_score": 1.0
                        })
                except Exception:
                    continue
            
            # Sort by end time (alerts ending soonest first)
            documents.sort(key=lambda x: x.get("end", ""))
            return documents[:top_k]
            
        except Exception as e:
            logger.error(f"Failed to retrieve alerts: {e}")
            return []
    
    def retrieve_current_conditions(self, location: str = None) -> List[Dict[str, Any]]:
        """Retrieve latest weather for a city - simple filter with server-side ordering."""
        try:
            from qdrant_client.models import OrderBy, Direction
            
            filter_conditions = [
                FieldCondition(key="data_type", match=MatchValue(value="current_weather"))
            ]
            if location:
                filter_conditions.append(
                    FieldCondition(key="location", match=MatchValue(value=location))
                )
            
            # Use server-side ordering by timestamp (descending) - much more efficient
            results = self.qdrant.scroll(
                collection_name=self.COLLECTION_NAME,
                scroll_filter=Filter(must=filter_conditions),
                limit=2,  # Only need top 2, server already sorted
                with_payload=True,
                order_by=OrderBy(key="timestamp", direction=Direction.DESC)
            )[0]
            
            if not results:
                return []
            
            # Already sorted by server, just convert to dict format
            documents = []
            for result in results:
                payload = result.payload
                documents.append({
                    "id": str(result.id),
                    "text": payload.get("text", ""),
                    "data_type": payload.get("data_type", "unknown"),
                    "timestamp": payload.get("timestamp", ""),
                    "location": payload.get("location", "Unknown"),
                    "raw_data": payload.get("raw_data", {}),
                    "final_score": 1.0,  # No similarity scoring needed
                    "source": payload.get("raw_data", {}).get("source", "unknown")
                })
            
            return documents
            
        except Exception as e:
            logger.error(f"Failed to retrieve current conditions: {e}")
            return []
    
    def retrieve_air_quality(self, location: str = None) -> List[Dict[str, Any]]:
        """Retrieve latest air quality for a city - simple filter with server-side ordering."""
        try:
            from qdrant_client.models import OrderBy, Direction
            
            # Build filter
            filter_conditions = [
                FieldCondition(key="data_type", match=MatchValue(value="air_quality"))
            ]
            if location:
                filter_conditions.append(
                    FieldCondition(key="location", match=MatchValue(value=location))
                )
            
            # Use server-side ordering by timestamp (descending) - much more efficient
            results = self.qdrant.scroll(
                collection_name=self.COLLECTION_NAME,
                scroll_filter=Filter(must=filter_conditions),
                limit=2,  # Only need top 2, server already sorted
                with_payload=True,
                order_by=OrderBy(key="timestamp", direction=Direction.DESC)
            )[0]
            
            if not results:
                return []
            
            # Already sorted by server, just convert to dict format
            documents = []
            for result in results:
                payload = result.payload
                documents.append({
                    "id": str(result.id),
                    "text": payload.get("text", ""),
                    "data_type": payload.get("data_type", "air_quality"),
                    "timestamp": payload.get("timestamp", ""),
                    "location": payload.get("location", "Unknown"),
                    "raw_data": payload.get("raw_data", {}),
                    "final_score": 1.0,
                    "source": "openweathermap"
                })
            
            return documents
            
        except Exception as e:
            logger.error(f"Failed to retrieve air quality: {e}")
            return []
    
    def retrieve_forecast(self, location: str = None, top_k: int = 3) -> List[Dict[str, Any]]:
        """Retrieve last 2-3 forecasts - simple filter/sort by timestamp, no RAG."""
        try:
            # Build filter
            filter_conditions = [
                FieldCondition(key="data_type", match=MatchValue(value="forecast"))
            ]
            if location:
                filter_conditions.append(
                    FieldCondition(key="location", match=MatchValue(value=location))
                )
            
            # Get entries
            results = self.qdrant.scroll(
                collection_name=self.COLLECTION_NAME,
                scroll_filter=Filter(must=filter_conditions),
                limit=50,
                with_payload=True
            )[0]
            
            # Parse timestamps and sort
            documents = []
            for point in results:
                payload = point.payload
                timestamp_str = payload.get("timestamp", "")
                
                try:
                    if 'T' in timestamp_str:
                        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        if timestamp.tzinfo:
                            timestamp = timestamp.replace(tzinfo=None)
                    else:
                        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    
                    documents.append({
                        "id": str(point.id),
                        "text": payload.get("text", ""),
                        "data_type": payload.get("data_type"),
                        "timestamp": timestamp_str,
                        "parsed_timestamp": timestamp,
                        "raw_data": payload,
                        "final_score": 1.0
                    })
                except Exception:
                    continue
            
            # Sort by timestamp (newest first) and return top_k
            documents.sort(key=lambda x: x["parsed_timestamp"], reverse=True)
            for doc in documents:
                del doc["parsed_timestamp"]  # Remove parsed field
            return documents[:top_k]
            
        except Exception as e:
            logger.error(f"Failed to retrieve forecast: {e}")
            return []
    
    def retrieve_news(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Retrieve news using TRUE RAG: semantic search + time weighting.
        
        This is the main RAG function per project spec:
        - Semantic similarity via embeddings (cosine similarity)
        - Time decay weighting (fresher = higher score)
        - NO hard age cutoff - all news considered, weighted by recency
        
        News is national (France-wide), not city-specific.
        """
        try:
            # Get query embedding
            query_embedding = self.embedding_model.embed(query)
            
            # Filter for news only
            filter_conditions = [
                FieldCondition(key="data_type", match=MatchValue(value="news"))
            ]
            
            # Retrieve more than needed for re-ranking
            results = self.qdrant.query_points(
                collection_name=self.COLLECTION_NAME,
                query=query_embedding,
                limit=top_k * 10,
                with_payload=True,
                query_filter=Filter(must=filter_conditions)
            ).points
            
            if not results:
                logger.info("No news found in Qdrant")
                return []
            
            # Apply time weighting (no hard age cutoff)
            documents = []
            now = datetime.utcnow()
            
            for result in results:
                payload = result.payload
                timestamp_str = payload.get("timestamp", "")
                
                # Calculate age in hours
                try:
                    if 'T' in timestamp_str:
                        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        if timestamp.tzinfo:
                            timestamp = timestamp.replace(tzinfo=None)
                    else:
                        timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    
                    age_hours = (now - timestamp).total_seconds() / 3600
                except Exception:
                    age_hours = 24  # Default to 1 day old
                
                # Time decay: fresher news scores higher (decay over 24 hours)
                time_decay = math.exp(-age_hours / 24)
                
                # Final score = similarity * time_decay
                similarity_score = result.score
                final_score = similarity_score * time_decay
                
                documents.append({
                    "id": str(result.id),
                    "text": payload.get("text", ""),
                    "data_type": "news",
                    "timestamp": timestamp_str,
                    "age_hours": round(age_hours, 1),
                    "raw_data": payload.get("raw_data", {}),
                    "similarity_score": round(similarity_score, 3),
                    "time_decay": round(time_decay, 3),
                    "final_score": round(final_score, 3),
                    "source": payload.get("raw_data", {}).get("source", "lemonde")
                })
            
            # Sort by final score (semantic relevance * recency)
            documents.sort(key=lambda x: x["final_score"], reverse=True)
            
            logger.info(f"Retrieved {len(documents)} news, returning top {top_k}")
            return documents[:top_k]
            
        except Exception as e:
            logger.error(f"Failed to retrieve news: {e}")
            return []
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the weather data collection."""
        try:
            collection = self.qdrant.get_collection(self.COLLECTION_NAME)
            # Handle different qdrant-client versions
            points = getattr(collection, 'points_count', None) or getattr(collection, 'vectors_count', 0)
            return {
                "vectors_count": points,
                "points_count": points,
                "status": getattr(collection.status, 'name', str(collection.status))
            }
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {"error": str(e)}

