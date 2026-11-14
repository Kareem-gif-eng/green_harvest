import json
import time
import urllib.request
import urllib.error
from dotenv import dotenv_values

key = dotenv_values(".env").get("GEMINI_API_KEY")
model = "gemini-3.5-flash-lite"

url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

payload = {
    "contents": [{
        "role": "user",
        "parts": [{"text": "رد بكلمة واحدة: مرحبا"}]
    }],
    "generationConfig": {
        "temperature": 0,
        "maxOutputTokens": 20
    }
}

req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "x-goog-api-key": key
    },
    method="POST"
)

print("MODEL:", model)
start = time.time()

try:
    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
        print("STATUS:", response.status)
        print("TIME:", round(time.time() - start, 2), "seconds")

        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            print("REPLY:", "".join(p.get("text", "") for p in parts))

except urllib.error.HTTPError as error:
    print("HTTP ERROR:", error.code)
    try:
        details = json.loads(error.read().decode("utf-8"))
        print("GOOGLE ERROR:", details.get("error", {}).get("status"))
        print("MESSAGE:", details.get("error", {}).get("message"))
    except Exception:
        print("Could not read error details")

except Exception as error:
    print("ERROR:", type(error).__name__, str(error))
    print("TIME:", round(time.time() - start, 2), "seconds")
