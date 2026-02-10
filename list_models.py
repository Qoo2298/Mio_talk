import os
import google.generativeai as genai

api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)

print("Listing all available Flash models...")
try:
    for m in genai.list_models():
        if 'flash' in m.name.lower():
            print(f"Model: {m.name}")
except Exception as e:
    print(f"Error: {e}")
