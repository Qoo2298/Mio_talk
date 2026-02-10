import requests
import json

url = "http://127.0.0.1:8003/api/chat"
payload = {"text": "ヤッホー！"}

print(f"Testing local API at {url}...")
try:
    response = requests.post(url, json=payload, timeout=20)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Connection to local API failed: {e}")
