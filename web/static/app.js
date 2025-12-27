// StormWatch AI - Frontend JavaScript

const API_BASE = '';

// Initialize markdown-it with HTML and table support
let md;
if (typeof markdownit !== 'undefined') {
    md = markdownit({
        html: true,
        breaks: true,
        linkify: true,
        typographer: true
    });
}

// State
let currentCity = 'Lyon';

// ============ INITIALIZATION ============

document.addEventListener('DOMContentLoaded', async () => {
    // Load cities first, then weather data
    await loadCities();
    loadWeather();
    loadAirQuality();
    loadAlerts();
    loadStats();

    // City selector change
    document.getElementById('city-select').addEventListener('change', (e) => {
        currentCity = e.target.value;
        loadWeather();
        loadAirQuality();
        loadAlerts();
        // Clear chat when city changes
        document.getElementById('chat-messages').innerHTML = '';
    });

    // Auto-refresh every 60 seconds
    setInterval(() => {
        loadWeather();
        loadAirQuality();
        loadAlerts();
        loadStats();
    }, 60000);
});

async function loadCities() {
    try {
        const res = await fetch(`${API_BASE}/api/cities`);
        const data = await res.json();

        const select = document.getElementById('city-select');
        select.innerHTML = data.cities.map(city =>
            `<option value="${city}"${city === currentCity ? ' selected' : ''}>${city}</option>`
        ).join('');

        // Set currentCity to first city if current is not in list
        if (!data.cities.includes(currentCity) && data.cities.length > 0) {
            currentCity = data.cities[0];
        }
    } catch (e) {
        console.error('Failed to load cities:', e);
        // Fallback to default
        const select = document.getElementById('city-select');
        select.innerHTML = '<option value="Lyon">Lyon</option>';
    }
}


// ============ API CALLS ============

async function loadWeather() {
    try {
        const res = await fetch(`${API_BASE}/api/weather/${currentCity}`);
        const data = await res.json();

        document.getElementById('temp').textContent = `${data.temperature.toFixed(1)}°C`;
        document.getElementById('humidity').textContent = `${data.humidity}%`;
        document.getElementById('wind').textContent = `${data.wind_speed} m/s`;
        document.getElementById('condition').textContent = data.description;

    } catch (e) {
        console.error('Failed to load weather:', e);
    }
}

async function loadAirQuality() {
    try {
        const res = await fetch(`${API_BASE}/api/air-quality/${currentCity}`);
        const data = await res.json();

        const badge = document.getElementById('aqi-badge');
        const label = document.getElementById('aqi-label');
        const pm25 = document.getElementById('pm25');

        badge.textContent = data.aqi || '--';
        label.textContent = data.aqi_label || 'Unknown';
        pm25.textContent = data.pm2_5 ? data.pm2_5.toFixed(1) : '--';

        // Set badge color based on AQI
        badge.className = 'aqi-badge';
        if (data.aqi === 1) badge.classList.add('good');
        else if (data.aqi === 2) badge.classList.add('fair');
        else if (data.aqi === 3) badge.classList.add('moderate');
        else if (data.aqi === 4) badge.classList.add('poor');
        else if (data.aqi === 5) badge.classList.add('very-poor');

    } catch (e) {
        console.error('Failed to load air quality:', e);
    }
}

async function loadAlerts() {
    try {
        const res = await fetch(`${API_BASE}/api/alerts?city=${currentCity}`);
        const alerts = await res.json();

        const container = document.getElementById('alerts-container');

        if (alerts.length > 0) {
            container.innerHTML = alerts.map(a =>
                `<div class="alert-badge warning">⚠️ ${a.event}</div>`
            ).join('');
        } else {
            container.innerHTML = '<div class="alert-badge clear">✅ No alerts</div>';
        }

    } catch (e) {
        console.error('Failed to load alerts:', e);
    }
}

async function loadStats() {
    try {
        const res = await fetch(`${API_BASE}/api/stats`);
        const data = await res.json();

        const dot = document.getElementById('status-dot');
        const text = document.getElementById('status-text');

        if (data.online) {
            dot.className = 'status-dot online';
            text.textContent = 'Live Data';
        } else {
            dot.className = 'status-dot offline';
            text.textContent = 'Offline';
        }

    } catch (e) {
        console.error('Failed to load stats:', e);
    }
}


// ============ CHAT FUNCTIONS ============

function handleKeyPress(event) {
    if (event.key === 'Enter') {
        sendMessage();
    }
}

function sendQuickQuestion(question) {
    document.getElementById('chat-input').value = question;
    sendMessage();
}

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();

    if (!message) return;

    // Clear input
    input.value = '';

    // Add user message
    addMessage('user', message);

    // Show loading
    const loadingId = showLoading();

    try {
        const res = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, city: currentCity })
        });

        const data = await res.json();

        // Remove loading
        removeLoading(loadingId);

        // Add assistant response
        addMessage('assistant', data.response);

    } catch (e) {
        removeLoading(loadingId);
        addMessage('assistant', '⚠️ Sorry, I encountered an error. Please try again.');
        console.error('Chat error:', e);
    }
}

function addMessage(role, content) {
    const container = document.getElementById('chat-messages');

    const avatar = role === 'user' ? '👤' : '🌪️';

    // Use markdown-it for markdown parsing (supports tables)
    let html;
    try {
        html = md ? md.render(content) : content;
    } catch (e) {
        // Fallback if markdown-it not loaded
        html = content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>');
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    messageDiv.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-content">${html}</div>
    `;

    container.appendChild(messageDiv);

    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
}

function showLoading() {
    const container = document.getElementById('chat-messages');
    const id = 'loading-' + Date.now();

    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message assistant';
    loadingDiv.id = id;
    loadingDiv.innerHTML = `
        <div class="message-avatar">🌪️</div>
        <div class="message-content">
            <div class="loading-dots">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;

    container.appendChild(loadingDiv);
    container.scrollTop = container.scrollHeight;

    return id;
}

function removeLoading(id) {
    const loading = document.getElementById(id);
    if (loading) {
        loading.remove();
    }
}
