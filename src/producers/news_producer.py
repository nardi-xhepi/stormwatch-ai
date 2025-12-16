"""France Info RSS News Producer for real-time weather news ingestion."""

import feedparser
import json
import logging
import argparse
import time
import hashlib
from datetime import datetime
from typing import Set, Dict, Any, Optional

from kafka import KafkaProducer

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.settings import get_settings

logger = logging.getLogger(__name__)


class NewsProducer:
    """Producer for French weather news from RSS feeds."""
    
    # Le Monde climat/météo RSS feed (working)
    RSS_FEEDS = [
        "https://www.lemonde.fr/climat/rss_full.xml",
    ]
    
    # Keywords to filter for weather-related content only (strict matching)
    WEATHER_KEYWORDS = [
        "vigilance", "alerte météo", "pluie", "neige", "orage",
        "tempête", "tempete", "inondation", "crue", "grand froid",
        "canicule", "grêle", "grele", "verglas", "brouillard",
        "tornade", "ouragan", "cyclone", "sécheresse", "secheresse",
        "météo-france", "meteo-france", "prévisions météo"
    ]
    
    TOPIC_NEWS = "weather-news"
    
    def __init__(self):
        self.settings = get_settings()
        self.seen_articles: Set[str] = set()  # Track seen article IDs
        
        # Initialize Kafka producer
        self.producer = KafkaProducer(
            bootstrap_servers=self.settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None
        )
        logger.info(f"News producer connected to Kafka at {self.settings.kafka_bootstrap_servers}")
    
    def _generate_article_id(self, article: Dict[str, Any]) -> str:
        """Generate a unique ID for an article based on its content."""
        unique_string = f"{article.get('link', '')}{article.get('title', '')}"
        return hashlib.md5(unique_string.encode()).hexdigest()
    
    def fetch_and_publish(self) -> int:
        """Fetch RSS feeds and publish new articles to Kafka.
        
        Returns:
            Number of new articles published
        """
        new_articles = 0
        
        for feed_url in self.RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                
                if feed.bozo:
                    logger.warning(f"Feed parsing issue for {feed_url}: {feed.bozo_exception}")
                    continue
                
                for entry in feed.entries:
                    article_id = self._generate_article_id(entry)
                    
                    # Skip if already seen
                    if article_id in self.seen_articles:
                        continue
                    
                    self.seen_articles.add(article_id)
                    
                    # Filter: only keep weather-related articles
                    title = entry.get("title", "").lower()
                    description = entry.get("summary", entry.get("description", "")).lower()
                    content = f"{title} {description}"
                    
                    if not any(keyword in content for keyword in self.WEATHER_KEYWORDS):
                        logger.debug(f"Skipped non-weather article: {entry.get('title', '')[:40]}...")
                        continue
                    
                    # Extract article data
                    article_data = {
                        "id": article_id,
                        "title": entry.get("title", ""),
                        "description": entry.get("summary", entry.get("description", "")),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", datetime.utcnow().isoformat()),
                        "source": "francetvinfo",
                        "category": "weather_news",
                        "timestamp": datetime.utcnow().isoformat(),
                        "ingestion_time": datetime.utcnow().isoformat(),
                        "data_type": "news"
                    }
                    
                    # Create text representation for embedding
                    article_data["text"] = f"{article_data['title']}. {article_data['description']}"
                    
                    # Publish to Kafka
                    self.producer.send(
                        self.TOPIC_NEWS,
                        key=article_id,
                        value=article_data
                    )
                    
                    logger.info(f"📰 Published news: {article_data['title'][:60]}...")
                    new_articles += 1
                    
            except Exception as e:
                logger.error(f"Error fetching feed {feed_url}: {e}")
        
        self.producer.flush()
        return new_articles
    
    def run_continuous(self, poll_interval: int = 30):
        """Run continuous polling of RSS feeds.
        
        Args:
            poll_interval: Seconds between polling (default 60s)
        """
        logger.info(f"Starting continuous news polling every {poll_interval}s...")
        
        while True:
            try:
                new_count = self.fetch_and_publish()
                if new_count > 0:
                    logger.info(f"Published {new_count} new articles")
                else:
                    logger.debug("No new articles found")
                    
                time.sleep(poll_interval)
                
            except KeyboardInterrupt:
                logger.info("Shutting down news producer...")
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                time.sleep(poll_interval)
        
        self.producer.close()
        logger.info("News producer closed")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description="France Info News Producer")
    parser.add_argument("--test-mode", action="store_true", help="Fetch once and exit")
    parser.add_argument("--interval", type=int, default=60, help="Poll interval in seconds")
    args = parser.parse_args()
    
    producer = NewsProducer()
    
    if args.test_mode:
        count = producer.fetch_and_publish()
        logger.info(f"Test mode: Published {count} articles")
        producer.producer.close()
    else:
        producer.run_continuous(args.interval)


if __name__ == "__main__":
    main()
