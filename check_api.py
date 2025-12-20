import os
import sys
import requests
from dotenv import load_dotenv

# Load env vars
load_dotenv()

api_key = os.getenv("OPENWEATHERMAP_API_KEY")
if not api_key:
    print("No API key found in .env")
    sys.exit(1)

# Check One Call 3.0
lat, lon = 45.7640, 4.8357 # Lyon
url = f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={api_key}&exclude=minutely,hourly,daily"

print(f"Testing URL: {url.replace(api_key, 'REDACTED')}")

response = requests.get(url)
print(f"Status Code: {response.status_code}")
if response.status_code == 200:
    print("Success! One Call API 3.0 is available.")
    data = response.json()
    if "alerts" in data:
        print(f"Alerts found: {len(data['alerts'])}")
    else:
        print("No active alerts currently for Lyon (expected).")
else:
    print(f"Error: {response.text}")
    print("One Call 3.0 might not be enabled. Trying 2.5 One Call...")
    
    url2 = f"https://api.openweathermap.org/data/2.5/onecall?lat={lat}&lon={lon}&appid={api_key}&exclude=minutely,hourly,daily"
    response2 = requests.get(url2)
    print(f"Status Code: {response2.status_code}")
    if response2.status_code == 200:
        print("Success! One Call API 2.5 is available.")
    else:
        print(f"Error: {response2.text}")
