import requests
import os
import sys

try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import config
    API_KEY = os.getenv("SARVAM_API_KEY", getattr(config, "SARVAM_API_KEY", None))
    BASE_URL = os.getenv("SARVAM_API_URL", getattr(config, "SARVAM_API_URL", ""))
except ImportError:
    API_KEY = os.getenv("SARVAM_API_KEY", None)
    BASE_URL = os.getenv("SARVAM_API_URL", "")

def call_llm(system_prompt, user_prompt, temperature=0.3, max_tokens=120):
    if not API_KEY or not BASE_URL:
        print("LLM not configured: SARVAM_API_KEY or SARVAM_API_URL missing.")
        return None
    headers = {
        "Content-Type": "application/json",
        "api-subscription-key": API_KEY
    }

    payload = {
        "model": "sarvam-m",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    try:
        print(f"Making LLM API call to: {BASE_URL}")
        print(f"API Key present: {'Yes' if API_KEY else 'No'}")
        print(f"System prompt length: {len(system_prompt)}")
        print(f"User prompt length: {len(user_prompt)}")
        
        response = requests.post(BASE_URL, headers=headers, json=payload, timeout=30)
        
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response data keys: {list(data.keys())}")
            
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"].strip()
                print(f"LLM response length: {len(content)}")
                print(f"LLM response preview: {content[:200]}...")
                return content
            else:
                print("Error: No choices in LLM response")
                print(f"Full response: {data}")
                return None
        else:
            print(f"HTTP Error: {response.status_code}")
            print(f"Response text: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Request Exception: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error in LLM call: {e}")
        return None