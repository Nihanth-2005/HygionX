"""
Generate follow-up questions using the LLM.

The LLM returns structured JSON so the UI can render proper answer types.
"""

import re
import json
import os
import sys

# Ensure the project root is on the path so llm_client can always be imported
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)


SYSTEM_PROMPT_BASE = """
You are a medical triage assistant.

Generate ONE follow-up question to clarify the patient's symptoms.

Return ONLY a JSON object with the following fields:

{
  "question": "...",
  "answer_type": "yes_no | multiple_choice | scale_1_10 | text",
  "options": ["..."],
  "allow_custom_answer": true
}

Rules:
- Ask only ONE question.
- The question must help clarify symptoms medically.
- If asking about severity use scale_1_10.
- If asking about presence of symptoms use yes_no.
- If asking about categories use multiple_choice.
- If asking for description use text.
- Keep options medically meaningful.
"""


USER_PROMPT_FEW_SYMPTOMS = """
User message: "{user_message}"

Detected symptoms so far: {symptoms_list}

Generate ONE follow-up question to better understand the patient's symptoms.
"""


USER_PROMPT_CLARIFY = """
User message: "{user_message}"

Detected symptoms: {symptoms_list}

Generate ONE follow-up question to clarify symptom details such as:
location, severity, duration, or related symptoms.
"""


def clean_llm_response(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.replace("<think>", "").replace("</think>", "")
    return text.strip()


def _parse_llm_followup(text: str):
    text = clean_llm_response(text)
    try:
        data = json.loads(text)
        return {
            "question": data.get("question"),
            "answer_type": data.get("answer_type", "text"),
            "options": data.get("options", []),
            "allow_custom_answer": data.get("allow_custom_answer", True)
        }
    except Exception:
        return None


def generate_followup_questions(
    user_message: str,
    detected_symptoms=None,
    max_questions: int = 3,
    has_some_symptoms: bool = False
):
    try:
        from llm.llm_client import call_llm

        symptoms = detected_symptoms or []
        symptoms_list = ", ".join(symptoms) if symptoms else "none"

        if not has_some_symptoms or len(symptoms) < 2:
            user_prompt = USER_PROMPT_FEW_SYMPTOMS.format(
                user_message=user_message,
                symptoms_list=symptoms_list
            )
        else:
            user_prompt = USER_PROMPT_CLARIFY.format(
                user_message=user_message,
                symptoms_list=symptoms_list
            )

        print("Calling LLM for follow-up question...")

        raw = call_llm(
            SYSTEM_PROMPT_BASE,
            user_prompt,
            temperature=0.3,
            max_tokens=200
        )

        if not raw:
            return {
                "question": "Can you describe your symptoms in more detail?",
                "answer_type": "text",
                "options": [],
                "allow_custom_answer": True
            }

        parsed = _parse_llm_followup(raw)

        if not parsed:
            return {
                "question": "Can you describe your symptoms in more detail?",
                "answer_type": "text",
                "options": [],
                "allow_custom_answer": True
            }

        return parsed

    except Exception as e:
        print(f"Warning: LLM follow-up generation failed ({e})")
        return {
            "question": "Can you describe your symptoms in more detail?",
            "answer_type": "text",
            "options": [],
            "allow_custom_answer": True
        }