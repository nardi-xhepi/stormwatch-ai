"""Response generator using Groq LLM."""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import get_settings
from src.rag.retriever import TemporalRetriever

logger = logging.getLogger(__name__)


class WeatherAdvisor:
    """Generates weather advisories using RAG with Groq."""
    
    SYSTEM_PROMPT = """You are StormWatch AI, a real-time severe weather advisory assistant. 
    Your role is to provide accurate, actionable weather information based STRICTLY on the retrieved context.

    CRITICAL RULES:
    1. NEVER start your response with "Current conditions" or similar generic introductions.
    2. Directly answer the user's question immediately.
    3. Be concise and to the point.
    4. STRICTLY GROUND your response in the provided context. DO NOT invent alerts, temperatures, or conditions.
    5. If the context contains NO alerts, explicitly state that there are no active alerts. DO NOT Hallucinate an alert.
    6. If the context is empty or irrelevant, state: "I don't have enough data to answer that specific question."
    7. Use markdown formatting for better readability.
    8. When citing news articles, ALWAYS include the article link so users can read more.

    Guidelines:
    1. Prioritize safety information.
    2. For severe weather, lead with the most critical information found in the context.
    3. Provide specific, actionable recommendations based ONLY on the known conditions.
    4. If data is outdated or incomplete, clearly state the limitations.
    5. For news, include the source link formatted as markdown: [Read more](url)

    Example good responses:
    - For "What's the weather?": "It's currently 12°C with partly cloudy skies. Wind is light at 3 m/s."
    - For "Will it rain?": "No rain is expected in the next few hours based on the forecast."
    - For news: "... [Read more](https://www.lemonde.fr/...)"""

    def __init__(self):
        self.settings = get_settings()
        self.retriever = TemporalRetriever()
        self._init_llm()
    
    def _init_llm(self):
        """Initialize the Groq model."""
        try:
            from groq import Groq
            
            if not self.settings.groq_api_key:
                logger.warning("Groq API key not set, using fallback responses")
                self.client = None
                return
            
            self.client = Groq(api_key=self.settings.groq_api_key)
            self.model_name = "openai/gpt-oss-120b"
            logger.info(f"Groq client initialized (model: {self.model_name})")
            
        except Exception as e:
            logger.error(f"Failed to initialize Groq: {e}")
            self.client = None
    
    def _format_context(self, documents: List[Dict[str, Any]]) -> str:
        """Format retrieved documents as context for the LLM."""
        if not documents:
            return "No recent weather data available."
        
        context_parts = ["=== RETRIEVED WEATHER DATA ===\n"]
        
        for i, doc in enumerate(documents, 1):
            data_type = doc.get("data_type", "unknown")
            timestamp = doc.get("timestamp", "unknown")
            text = doc.get("text", "")
            score = doc.get("final_score", 0)
            
            # Calculate age
            try:
                if 'T' in timestamp:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    age = datetime.utcnow() - dt.replace(tzinfo=None)
                    age_str = f"{int(age.total_seconds() / 60)} minutes ago"
                else:
                    age_str = timestamp
            except:
                age_str = timestamp
            
            context_parts.append(f"[{i}] {data_type.upper()} (relevance: {score:.2f}, updated: {age_str})")
            context_parts.append(f"    {text}")
            
            # Add link for news articles
            raw_data = doc.get("raw_data", {})
            if data_type == "news" and raw_data.get("link"):
                context_parts.append(f"    Link: {raw_data.get('link')}")
            context_parts.append("")
        
        return "\n".join(context_parts)
    
    def generate_response(
        self,
        query: str,
        location: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate a weather advisory response using RAG.
        
        Args:
            query: User's question
            location: Optional location context
            
        Returns:
            Dictionary with response and metadata
        """
        logger.info(f"Processing query: {query} for location: {location}")
        
        current = self.retriever.retrieve_current_conditions(location)
        air_quality = self.retriever.retrieve_air_quality(location)
        alerts = self.retriever.retrieve_alerts(location=location)
        forecasts = self.retriever.retrieve_forecast(location=location, top_k=3)
        news = self.retriever.retrieve_news(query=query, top_k=3)
        
        context_docs = []
        if current:
            context_docs.append(current[0])
        if air_quality:
            context_docs.append(air_quality[0])
        context_docs.extend(forecasts[:2])
        context_docs.extend(alerts[:2])
        context_docs.extend(news[:3])
        
        logger.info(f"Context: {len(current)} current, {len(forecasts)} forecasts, {len(alerts)} alerts, {len(news)} news")
        
        context = self._format_context(context_docs)
        
        prompt = f"""{self.SYSTEM_PROMPT}

{context}

=== USER QUERY ===
Location: {location or 'Not specified'}
Question: {query}

Please provide a helpful, accurate response based on the retrieved weather data above. Be concise but informative."""

        # Generate response with retry logic
        generated_text = None
        
        if self.client:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[
                            {"role": "system", "content": self.SYSTEM_PROMPT},
                            {"role": "user", "content": f"{context}\n\n=== USER QUERY ===\nLocation: {location or 'Not specified'}\nQuestion: {query}\n\nPlease provide a helpful, accurate response based on the retrieved weather data above. Be concise but informative."}
                        ],
                        temperature=0.7,
                        max_tokens=1024
                    )
                    generated_text = response.choices[0].message.content
                    break
                except Exception as e:
                    error_msg = str(e)
                    if "429" in error_msg or "rate" in error_msg.lower():
                        # Rate limited - wait and retry
                        wait_time = min(10, 2 ** attempt)
                        logger.warning(f"Rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            time.sleep(wait_time)
                        else:
                            logger.warning("Using fallback response due to rate limits")
                            generated_text = self._fallback_response(query, context_docs)
                    else:
                        logger.error(f"LLM generation failed: {e}")
                        generated_text = self._fallback_response(query, context_docs)
                        break
        else:
            generated_text = self._fallback_response(query, context_docs)
        
        return {
            "response": generated_text,
            "query": query,
            "location": location,
            "sources": [
                {
                    "type": doc["data_type"],
                    "timestamp": doc["timestamp"],
                    "relevance": doc.get("final_score", 1.0)
                }
                for doc in context_docs[:6]
            ],
            "has_alerts": any(doc["data_type"] == "alert" for doc in context_docs),
            "generated_at": datetime.utcnow().isoformat()
        }
    
    def _fallback_response(self, query: str, documents: List[Dict[str, Any]]) -> str:
        """Generate a detailed response without LLM (for when Gemini is rate-limited)."""
        if not documents:
            return (
                "📡 **No recent weather data available.**\n\n"
                "Please ensure the weather data pipeline is running:\n"
                "1. Weather Producer: `python -m src.producers.weather_producer`\n"
                "2. Vector Consumer: `python -m src.consumers.vector_consumer`"
            )
        
        response_parts = []
        
        # Add alerts first (most important)
        alerts = [d for d in documents if d["data_type"] == "alert"]
        if alerts:
            response_parts.append("## ⚠️ Active Weather Alerts\n")
            for alert in alerts:
                raw = alert.get("raw_data", {})
                response_parts.append(f"**{raw.get('event', 'Alert')}** ({raw.get('severity', 'Unknown')} severity)")
                response_parts.append(f"> {raw.get('description', 'No details available')}\n")
        
        # Add current conditions
        current = [d for d in documents if d["data_type"] == "current_weather"]
        if current:
            response_parts.append("## 🌡️ Current Conditions\n")
            raw = current[0].get("raw_data", {})
            weather = raw.get("weather", {})
            
            response_parts.append(f"**{weather.get('description', 'Unknown').title()}**")
            response_parts.append(f"- Temperature: **{raw.get('temperature', 'N/A')}°C** (feels like {raw.get('feels_like', 'N/A')}°C)")
            response_parts.append(f"- Humidity: {raw.get('humidity', 'N/A')}%")
            response_parts.append(f"- Wind: {raw.get('wind_speed', 'N/A')} m/s")
            response_parts.append(f"- Visibility: {raw.get('visibility', 'N/A')}m\n")
        
        # Add forecast summary
        forecasts = [d for d in documents if d["data_type"] == "forecast"]
        if forecasts:
            response_parts.append("## 📅 Forecast Summary\n")
            raw = forecasts[0].get("raw_data", {})
            fc_list = raw.get("forecasts", [])[:4]  # Next 12 hours
            if fc_list:
                for fc in fc_list:
                    time = fc.get("timestamp", "")[:16] if fc.get("timestamp") else "N/A"
                    desc = fc.get("weather", {}).get("description", "Unknown")
                    temp = fc.get("temperature", "N/A")
                    pop = fc.get("pop", 0)
                    response_parts.append(f"- {time}: {desc.title()}, {temp}°C, {pop}% rain chance")
        
        # Add air quality if available
        aq = [d for d in documents if d["data_type"] == "air_quality"]
        if aq:
            raw = aq[0].get("raw_data", {})
            response_parts.append(f"\n## 🌬️ Air Quality: **{raw.get('aqi_label', 'Unknown')}** (AQI: {raw.get('aqi', 'N/A')})")
        
        if not response_parts:
            response_parts.append("Weather data is being collected. Please wait a moment and try again.")
        
        return "\n".join(response_parts)
    
    def get_quick_summary(self, location: Optional[str] = None) -> str:
        """Get a quick weather summary without detailed RAG."""
        current = self.retriever.retrieve_current_conditions(location)
        alerts = self.retriever.retrieve_alerts(top_k=1)
        
        if not current:
            return "No weather data available. Please ensure the data pipeline is running."
        
        summary = current[0]["text"]
        if alerts:
            summary = f"⚠️ ALERT: {alerts[0]['raw_data'].get('event', 'Weather Alert')}\n\n{summary}"
        
        return summary
