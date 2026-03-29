import requests
import re


class WikiRetriever:

    BASE_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"

    def __init__(self):
        self.headers = {
            "User-Agent": "SmartTriageSystem/1.0 (your-email@example.com)"
        }
        self.cache = {}
    
    def extract_disease_name(self, text):
        text = text.lower()

        patterns = [
            r"tell me about",
            r"what is",
            r"explain",
            r"information about",
            r"define",
            r"give details about"
        ]

        for p in patterns:
            text = re.sub(p, "", text)

        text = text.replace("?", "").strip()
        return text

    def retrieve(self, user_input, max_sentences=5):
        disease_name = self.extract_disease_name(user_input)
        if not disease_name:
            return "Please provide a disease name."

        formatted_name = disease_name.replace(" ", "_")

        if formatted_name in self.cache:
            return self.cache[formatted_name]

        try:
            response = requests.get(
                self.BASE_URL + formatted_name,
                headers=self.headers
            )

            if response.status_code != 200:
                return "Sorry, I couldn't find reliable information for that condition."

            data = response.json()

            if "extract" not in data:
                return "No summary available for this condition."

            text = data["extract"]

            sentences = re.split(r'(?<=[.!?])\s+', text)
            trimmed = " ".join(sentences[:max_sentences]).strip()

            self.cache[formatted_name] = trimmed

            return trimmed

        except Exception:
            return "Unable to retrieve information at this time."