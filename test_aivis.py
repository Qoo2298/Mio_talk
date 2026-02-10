import requests
import json

url = "http://localhost:10101/speakers"
print(f"Testing Aivis Speech at {url}...")
try:
    response = requests.get(url, timeout=5)
    print(f"Status: {response.status_code}")
    speakers = response.json()
    print(f"Found {len(speakers)} speakers.")
    # Look for Kohaku (1878365376)
    kohaku = [s for s in speakers if s['name'] == 'コハク']
    if kohaku:
        print("Speaker 'コハク' found!")
    else:
        print("Speaker 'コハク' NOT found. Available speakers:", [s['name'] for s in speakers[:5]])
except Exception as e:
    print(f"Connection failed: {e}")
