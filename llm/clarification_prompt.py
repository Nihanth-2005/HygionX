def build_clarification_prompt(intent):
    prompts = {
        "neurological": "Ask one short question to check for serious neurological red flags (like stroke). Keep it under 15 words.",
        "cardiac": "Ask one short question to check for serious cardiac warning signs. Keep it under 15 words.",
        "respiratory": "Ask one short question to check for breathing-related emergencies. Keep it under 15 words.",
        "abdominal": "Ask one short question to assess severity of abdominal symptoms. Keep it under 15 words.",
        "infection": "Ask one short question about duration and severity of infection symptoms. Keep it under 15 words."
    }

    return prompts.get(intent, None)