# Data Streaming Project: Real-Time Weather RAG

**Course Project - M2 Data Science**

A real-time weather advisory system using Apache Kafka, Qdrant, and RAG.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Apache Kafka](https://img.shields.io/badge/Apache%20Kafka-3.x-black.svg)](https://kafka.apache.org/)
[![Qdrant](https://img.shields.io/badge/Qdrant-Vector%20DB-red.svg)](https://qdrant.tech/)

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Installation](#installation)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [API Endpoints](#api-endpoints)
- [Configuration](#configuration)
- [Team](#team)

## 🌟 Overview

This project implements a real-time weather monitoring system. It demonstrates a data streaming architecture by ingesting weather data from OpenWeatherMap, processing it through Apache Kafka, and storing vector embeddings in Qdrant for retrieval. A RAG (Retrieval-Augmented Generation) chatbot uses this data to answer user queries about the weather.

**Key Technologies:**
- **Apache Kafka**: Real-time data streaming
- **Qdrant**: Vector database
- **Groq LLM**: Text generation
- **FastAPI**: Backend API
- **Sentence Transformers**: Embeddings

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  OpenWeatherMap │────▶│  Kafka Producer │────▶│   Kafka Topics  │
│       API       │     │                 │     │  (weather-data) │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Web Frontend  │◀────│   FastAPI       │◀────│ Vector Consumer │
│   (HTML/JS/CSS) │     │   Backend       │     │   + Embeddings  │
└─────────────────┘     └────────┬────────┘     └────────┬────────┘
                                 │                       │
                                 ▼                       ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │   RAG System    │◀────│     Qdrant      │
                        │  (Retriever +   │     │  Vector Database│
                        │   Generator)    │     │                 │
                        └─────────────────┘     └─────────────────┘
```

**Data Flow:**
1. **Kafka Producer** polls OpenWeatherMap API every 2 minutes for 5 French cities
2. Weather data is published to Kafka topics
3. **Vector Consumer** consumes messages, generates embeddings, stores in Qdrant
4. **Web Frontend** reads weather data from Qdrant (not direct API)
5. **RAG Chatbot** retrieves relevant weather context and generates responses



## 🛠️ Installation

### Prerequisites

- Python 3.10+
- Apache Kafka (via Docker or local installation)
- Qdrant Cloud account or local Qdrant instance

### Setup

1. **Clone the repository:**
```bash
git clone https://github.com/nardi-xhepi/stormwatch-ai.git
cd stormwatch-ai
```

2. **Create virtual environment:**
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or .venv\Scripts\activate  # Windows
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Configure environment variables:**
```bash
cp .env.example .env
# Edit .env with your API keys:
# - OPENWEATHERMAP_API_KEY
# - GROQ_API_KEY
# - QDRANT_HOST and QDRANT_API_KEY
```

### Quick Start with Docker (Recommended) 🐳

1. **Clone the repository:**
```bash
git clone https://github.com/nardi-xhepi/stormwatch-ai.git
cd stormwatch-ai
```

2. **Configure environment variables:**
```bash
cp .env.example .env
# Edit .env with your API keys:
# - OPENWEATHERMAP_API_KEY
# - GROQ_API_KEY
```

3. **Run with Docker Compose:**
```bash
docker compose up --build
```

Access the application at **http://localhost:8000**.

### Manual Installation (Local Dev)

1. **Prerequisites:**
   - Python 3.10+
   - Apache Kafka (or use Docker for Kafka only)
   - Qdrant (or use Docker for Qdrant only)

2. **Setup:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. **Run Services Manually:**
```bash
# Terminal 1: Kafka Producer
python -m src.producers.weather_producer

# Terminal 2: Vector Consumer
python -m src.consumers.vector_consumer

# Terminal 3: Web API
python -m web.api
```

**Access the application:**
Open http://localhost:8000 in your browser.

### Example Queries

- "What is the current weather in Lyon?"
- "Is it safe to drive in Paris?"
- "What's the temperature in Marseille?"
- "Will it rain today?"

## 📁 Project Structure

```
stormwatch-ai/
├── config/
│   └── settings.py          # Pydantic settings management
├── src/
│   ├── api/
│   │   └── weather_client.py # OpenWeatherMap API client
│   ├── producers/
│   │   └── weather_producer.py # Kafka producer
│   ├── consumers/
│   │   └── vector_consumer.py  # Kafka consumer + Qdrant
│   └── rag/
│       ├── embeddings.py      # Sentence-transformers wrapper
│       ├── retriever.py       # Temporal retriever with Qdrant
│       └── generator.py       # Groq LLM response generator
├── web/
│   ├── api.py                # FastAPI backend
│   └── static/
│       ├── index.html        # Main web page
│       ├── styles.css        # Styling
│       └── app.js           # Frontend JavaScript
├── docker-compose.yml        # Kafka setup
├── requirements.txt          # Python dependencies
├── .env.example             # Environment template
└── README.md                # This file
```

## 🔌 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve web frontend |
| `/api/weather/{city}` | GET | Get current weather from Qdrant |
| `/api/alerts` | GET | Get active weather alerts |
| `/api/stats` | GET | Get system statistics |
| `/api/chat` | POST | Chat with the weather assistant |

## ⚙️ Configuration

Key environment variables in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENWEATHERMAP_API_KEY` | API key for weather data | Required |
| `GROQ_API_KEY` | API key for LLM responses | Required |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker address | localhost:9093 |
| `QDRANT_HOST` | Qdrant server URL | Qdrant Cloud URL |
| `QDRANT_API_KEY` | Qdrant API key | Required for cloud |
| `WEATHER_POLL_INTERVAL` | Update frequency (seconds) | 120 |

## 👥 Team

| Name | Role |
|------|------|
| **Nardi XHEPI** | Developer |
| **Augustin BRESSET** | Developer |

## 📄 License

This project was developed as part of a Data Streaming course project.

---

*M2 Data Science - Data Streaming Project* 🌤️
