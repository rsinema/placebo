"""Quick test for Moonshot API connectivity."""

import os
from openai import OpenAI

api_key = os.environ.get("MOONSHOT_API_KEY", "")
if not api_key:
    print("ERROR: Set MOONSHOT_API_KEY environment variable first")
    print("  export MOONSHOT_API_KEY=sk-your-key-here")
    raise SystemExit(1)

client = OpenAI(api_key=api_key, base_url="https://api.moonshot.ai/v1")

print("Sending test request to Moonshot API...")
response = client.chat.completions.create(
    model="moonshot-v1-8k",
    messages=[{"role": "user", "content": "Say hello in one sentence."}],
    max_tokens=50,
)
print(f"Success! Response: {response.choices[0].message.content}")
