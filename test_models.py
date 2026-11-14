import json
import time
import urllib.request
from dotenv import dotenv_values

key = dotenv_values(".env").get("GEMINI_API_KEY")

req = urllib.request.Request(
    "https://generativelanguage.googleapis.com/v1beta/models",
    headers={"x-goog-api-key": key}
)

start = time.time()

try:
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

        print("STATUS:", response.status)
        print("TIME:", round(time.time() - start, 2))

        for model in data.get("models", []):
            name = model.get("name", "")
            methods = model.get("supportedGenerationMethods", [])

            if "generateContent" in methods and "flash" in name.lower():
                print(name, "|", methods)

except Exception as error:
    print("ERROR:", type(error).__name__, str(error))
