import json
import time
import urllib.request
import urllib.error
from dotenv import dotenv_values

config = dotenv_values(".env")
api_key = config.get("GEMINI_API_KEY")
model = config.get("GEMINI_MODEL", "gemini-3.8-flash")

if not api_key:
    print("ERROR: GEMINI_API_KEY is missing")
    raise SystemExit(1)

url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

payload = {
    "contents": [
        {
            "role": "user",
            "parts": [{"text": "رد بكلمة واحدة: مرحبا"}]
        }
    ],
    "generationConfig": {
        "temperature": 0,
        "maxOutputTokens": 30
    }
}

request = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    },
    method="POST"
)

print("Model:", model)
print("Starting direct Gemini test...")

start = time.time()

try:
    with urllib.request.urlopen(request, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
        print("HTTP STATUS:", response.status)
        print("TIME:", round(time.time() - start, 2), "seconds")
        print("CANDIDATES:", len(data.get("candidates", [])))
        print("RESULT: SUCCESS")

except urllib.error.HTTPError as error:
    print("HTTP STATUS:", error.code)
    print("TIME:", round(time.time() - start, 2), "seconds")
    try:
        details = json.loads(error.read().decode("utf-8"))
        print("GOOGLE ERROR:", details.get("error", {}).get("status"))
        print("MESSAGE:", details.get("error", {}).get("message"))
    except Exception:
        print("Could not read error details")

except Exception as error:
    print("ERROR TYPE:", type(error).__name__)
    print("ERROR:", str(error))
    print("TIME:", round(time.time() - start, 2), "seconds")
