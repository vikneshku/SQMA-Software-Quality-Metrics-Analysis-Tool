import os
import time
from config import BASE_DIR
from google import genai

api_key = os.getenv("GEMINI_API_KEY")
if not api_key or api_key == "your_actual_api_key_here":
    raise RuntimeError("GEMINI_API_KEY is missing or using placeholder in .env")

client = genai.Client(api_key=api_key)

# Standard supported Gemini models
models = [
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-flash-latest",
]

for model in models:
    for attempt in range(2):
        try:
            print(f"Testing model: {model}")
            response = client.models.generate_content(
                model=model,
                contents="Reply with: Gemini connection successful"
            )
            print("SUCCESS:", response.text)
            raise SystemExit(0)

        except SystemExit:
            raise

        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")

            if attempt == 0:
                time.sleep(3)

    print(f"Trying the next model...")

raise RuntimeError(
    "All model attempts failed. Check the errors above."
)