import os
import requests
import google.generativeai as genai

def diagnose():
    print("--- MIO v1 DIAGNOSTICS ---")
    
    # 1. Check Library
    try:
        import google.generativeai
        print("[OK] google-generativeai library is installed.")
    except ImportError:
        print("[FAIL] google-generativeai library is NOT installed.")
        return

    # 2. Check Environment Variable
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        print(f"[OK] GEMINI_API_KEY is set. (Length: {len(api_key)})")
    else:
        print("[FAIL] GEMINI_API_KEY is NOT set in this process environment.")
        return

    # 3. Test Gemini Connection
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content("hello", generation_config={"max_output_tokens": 5})
        print(f"[OK] Gemini API test success: {response.text.strip()}")
    except Exception as e:
        print(f"[FAIL] Gemini API connection error: {e}")

    # 4. Test Aivis Speech
    try:
        res = requests.get("http://localhost:10101/version", timeout=3)
        print(f"[OK] Aivis Speech is running. (Version: {res.text})")
    except Exception as e:
        print(f"[FAIL] Aivis Speech connection error: {e}")

diagnose()
