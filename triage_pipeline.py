"""
HygionX triage pipeline.
Flow: extract symptoms → check red flags → merge with previous → if emergency return;
      if symptom count < 2 → follow-up questions; else → full triage.
"""

import re

# Placeholder that counts as "no specific symptom"
GENERAL_SYMPTOM_PLACEHOLDER = "general symptoms (from your description)"

# Red-flag phrases
RED_FLAG_PHRASES = [
    "chest pain",
    "severe breathlessness",
    "shortness of breath",
    "can't breathe",
    "loss of consciousness",
    "passed out",
    "unconscious",
    "stroke",
    "slurred speech",
    "facial droop",
    "severe bleeding",
    "heavy bleeding",
    "suicidal",
    "suicide",
    "kill myself",
    "severe allergic reaction",
    "anaphylaxis",
    "throat closing",
    "can't swallow",
]

EMERGENCY_MESSAGE = (
    "Your symptoms may indicate a medical emergency. "
    "Please seek immediate medical attention or contact emergency services."
)

MEDICAL_DISCLAIMER = (
    "This AI provides guidance only and is not a substitute for professional medical diagnosis."
)

# Emergency override symptoms - these trigger EMERGENCY classification
EMERGENCY_OVERRIDE_SYMPTOMS = [
    "severe chest pain",
    "chest pain",
    "breathing difficulty",
    "shortness of breath",
    "can't breathe",
    "difficulty breathing",
    "loss of consciousness",
    "fainted",
    "unconscious",
    "stroke symptoms",
    "face drooping",
    "arm weakness",
    "speech difficulty",
    "severe bleeding",
    "bleeding heavily",
    "uncontrolled bleeding",
]

# Stroke-specific symptoms for emergency override
STROKE_SYMPTOMS = [
    "face drooping",
    "arm weakness",
    "speech difficulty",
    "slurred speech",
    "confusion",
    "one-sided weakness",
    "numbness on one side",
]


def _normalize_questions(raw_questions):
    """
    Ensure follow-up questions are always returned as a list of strings.
    Handles dict, string, or malformed LLM output.
    """

    if not raw_questions:
        return []

    if isinstance(raw_questions, str):
        return [raw_questions.strip()]

    if isinstance(raw_questions, dict):
        q = raw_questions.get("question")
        return [q] if q else []

    if isinstance(raw_questions, list):
        cleaned = []
        for q in raw_questions:
            if isinstance(q, str):
                cleaned.append(q.strip())
            elif isinstance(q, dict) and "question" in q:
                cleaned.append(q["question"].strip())
        return cleaned

    return []


def _clean_llm_output(text: str):
    """Remove <think>...</think> blocks from LLM output."""
    if not text:
        return text
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _count_real_symptoms(symptoms: list) -> int:
    if not symptoms:
        return 0
    only_placeholder = (
        len(symptoms) == 1 and symptoms[0].lower() == GENERAL_SYMPTOM_PLACEHOLDER.lower()
    )
    if only_placeholder:
        return 0
    return len(symptoms)


def _merge_symptoms(previous: list, new: list) -> list:
    seen = set()
    out = []

    for s in (previous or []) + (new or []):
        key = (s or "").strip().lower()

        if not key or key == GENERAL_SYMPTOM_PLACEHOLDER.lower():
            continue

        if key in seen:
            continue

        seen.add(key)
        out.append(s.strip())

    return out


def _check_red_flags(text: str, symptoms: list) -> bool:

    t = (text or "").lower()

    combined = t + " " + " ".join((s or "").lower() for s in (symptoms or []))

    for phrase in RED_FLAG_PHRASES:
        if phrase in combined:
            return True

    return False


def _check_emergency_override(text: str, symptoms: list) -> bool:
    """
    Check if symptoms include any emergency override triggers.
    These include severe chest pain, breathing difficulty, stroke symptoms,
    severe bleeding, or loss of consciousness.
    """
    t = (text or "").lower()
    
    combined = t + " " + " ".join((s or "").lower() for s in (symptoms or []))
    
    for phrase in EMERGENCY_OVERRIDE_SYMPTOMS:
        if phrase in combined:
            return True
    
    # Also check for stroke symptoms specifically
    stroke_found = 0
    for stroke_symptom in STROKE_SYMPTOMS:
        if stroke_symptom in combined:
            stroke_found += 1
    
    # If 2+ stroke symptoms found, trigger emergency
    if stroke_found >= 2:
        return True
    
    return False


def _get_urgency_level(severity_score: int, symptoms: list, text: str) -> str:
    """
    Determine urgency level based on severity score and symptoms.
    Returns: "Low Risk", "Moderate Risk", "High Risk", or "Emergency"
    """
    # Check for emergency override first
    if _check_emergency_override(text, symptoms):
        return "Emergency"
    
    if severity_score >= 8:
        return "High Risk"
    elif severity_score >= 5:
        return "Moderate Risk"
    else:
        return "Low Risk"


def _get_possible_conditions_with_probabilities(text: str, symptoms: list) -> list:
    """
    Generate up to 3 possible conditions with probability percentages.
    Percentages must sum to 100%.
    Base probabilities on symptom overlap and medical plausibility.
    """
    t = (text or "").lower()
    symptoms_lower = [s.lower() for s in (symptoms or [])]
    symptoms_text = " ".join(symptoms_lower)
    
    # Cardiovascular/Respiratory emergencies
    if "chest" in t or "chest pain" in symptoms_text or "shortness of breath" in symptoms_text:
        return [
            "Acute coronary syndrome (rule out)",
            "Pulmonary embolism (rule out)",
            "Anxiety or musculoskeletal chest pain"
        ]
    
    # Respiratory symptoms
    if "cough" in t or "coughing" in t:
        if "fever" in t:
            return [
                "Viral upper respiratory infection",
                "COVID-19 (rule out)",
                "Influenza"
            ]
        return [
            "Upper respiratory infection",
            "Allergic rhinitis",
            "Asthma (rule out)"
        ]
    
    # Fever with throat symptoms
    if "fever" in t and ("throat" in t or "sore throat" in symptoms_text):
        return [
            "Viral upper respiratory infection",
            "COVID-19 (rule out)",
            "Strep throat (rule out)"
        ]
    
    # Fever alone
    if "fever" in t or "high temperature" in t:
        return [
            "Viral infection",
            "COVID-19 (rule out)",
            "Influenza"
        ]
    
    # Gastrointestinal symptoms
    if "stomach" in t or "abdominal" in t or "nausea" in t or "vomiting" in t:
        return [
            "Gastroenteritis",
            "Functional abdominal pain",
            "Other GI causes (rule out)"
        ]
    
    # Headache
    if "headache" in t or "head ache" in t:
        return [
            "Tension-type headache",
            "Migraine",
            "Viral illness"
        ]
    
    # Default - mild symptoms
    return [
        "Viral or mild illness",
        "Condition to be assessed by clinician",
        "Monitor and follow up"
    ]


def _distribute_probabilities(conditions: list) -> list:
    """
    Distribute probabilities among conditions.
    Higher probabilities for conditions that are more common/likely.
    Percentages must sum to 100%.
    """
    if not conditions:
        return []
    
    n = len(conditions)
    
    # Use a distribution that gives higher probability to first conditions
    # but ensures all have meaningful probability
    if n == 3:
        # 45%, 35%, 20%
        return [45, 35, 20]
    elif n == 2:
        # 60%, 40%
        return [60, 40]
    else:
        # 100%
        return [100]


def _get_llm_recommendations(symptoms: list, urgency: str, conditions: list, severity_score: int) -> str:
    """
    Generate recommendations using LLM based on symptoms, urgency, and possible conditions.
    This replaces directly printing diseases with LLM-generated guidance.
    """
    try:
        from llm.llm_client import call_llm
        
        symptoms_str = ", ".join(symptoms) if symptoms else "General symptoms"
        conditions_str = ", ".join(conditions) if conditions else "Unknown"
        
        system_prompt = """You are MediAI Triage, an AI-powered medical symptom assessment assistant.

IMPORTANT RULES:
1. NEVER provide definitive medical diagnoses
2. ALWAYS include a medical disclaimer
3. Generate helpful, actionable recommendations based on the urgency level
4. Use the symptoms and possible conditions to provide personalized guidance
5. Keep recommendations concise and practical

Your response should ONLY contain the recommendations, no additional text or formatting."""

        user_prompt = f"""Based on the following patient information, provide appropriate recommendations:

Symptoms: {symptoms_str}
Urgency Level: {urgency}
Severity Score: {severity_score}/10
Possible Conditions: {conditions_str}

Provide recommendations that are:
- Specific to the urgency level
- Practical and actionable
- Include when to seek further care
- Include self-care tips where appropriate

Do NOT mention specific diseases in your response - focus on recommendations and guidance."""

        response = call_llm(system_prompt, user_prompt, temperature=0.3, max_tokens=200)
        
        if response:
            # Clean the response
            response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
            return response
        else:
            return _get_default_recommendations(urgency, severity_score)
            
    except Exception as e:
        print(f"Error getting LLM recommendations: {e}")
        return _get_default_recommendations(urgency, severity_score)


def _get_default_recommendations(urgency: str, severity_score: int) -> str:
    """
    Get default recommendations when LLM is unavailable.
    """
    if urgency == "Emergency":
        return "Seek immediate emergency medical care. Call emergency services or go to the nearest emergency department immediately."
    elif urgency == "High Risk":
        return "Seek urgent medical attention within the next few hours. Consider visiting an urgent care clinic or emergency department if symptoms worsen."
    elif urgency == "Moderate Risk":
        return "Consider scheduling a medical appointment within 24-48 hours. Monitor symptoms and seek care if they worsen."
    else:
        return "Rest and stay hydrated. Monitor symptoms; seek medical advice if they persist or worsen."


def _get_extract_symptoms():

    try:
        from model_loader import models_loaded

        if not models_loaded():
            return None

        from symptom_extraction_pipeline import extract_symptoms

        return extract_symptoms

    except Exception:
        return None


def _extract_symptoms_rulebased(t: str):

    keywords = []

    symptom_map = {
        "fever": "fever",
        "headache": "headache",
        "head ache": "headache",
        "cough": "cough",
        "coughing": "cough",
        "chest pain": "chest pain",
        "chest tightness": "chest pain",
        "stomach pain": "stomach pain",
        "abdominal pain": "stomach pain",
        "sore throat": "sore throat",
        "shortness of breath": "shortness of breath",
        "short of breath": "shortness of breath",
        "nausea": "nausea",
        "vomiting": "vomiting",
        "fatigue": "fatigue",
        "dizziness": "dizziness",
    }

    for phrase, label in symptom_map.items():

        if phrase in t and label not in keywords:
            keywords.append(label)

    if not keywords:
        keywords = [GENERAL_SYMPTOM_PLACEHOLDER]

    return keywords


def _score_severity(t: str, symptoms: list):

    high_triggers = ["chest pain", "shortness of breath", "short of breath", "can't breathe"]

    mod_triggers = ["fever", "sore throat", "stomach pain", "vomiting", "severe"]

    score = 3

    for w in high_triggers:
        if w in t:
            return min(9, score + 6)

    for w in mod_triggers:
        if w in t:
            score += 2

    return min(10, max(1, score))


def _get_precautions(severity_score: int, t: str):

    if severity_score >= 7:

        return [
            "Seek urgent or emergency care if symptoms worsen",
            "Avoid strenuous activity",
            "Have someone stay with you if possible",
        ]

    if severity_score >= 5:

        return [
            "Consider a clinic or telehealth visit within 24–48 hours",
            "Rest and stay hydrated",
            "Monitor temperature and symptoms",
        ]

    return [
        "Rest and stay hydrated",
        "Monitor symptoms; seek care if they worsen",
        "Over-the-counter options may help (follow label instructions)",
    ]


def _get_possible_diseases(t: str, symptoms: list):

    if "chest" in t or "shortness of breath" in t or "short of breath" in t:

        return [
            "Acute coronary syndrome (rule out)",
            "Pulmonary embolism (rule out)",
            "Anxiety or musculoskeletal chest pain",
        ]

    if "fever" in t and ("throat" in t or "cough" in t):

        return [
            "Viral upper respiratory infection",
            "COVID-19 (rule out)",
            "Influenza",
            "Strep throat (rule out)",
        ]

    if "fever" in t:
        return ["Viral infection", "COVID-19 (rule out)", "Influenza"]

    if "stomach" in t or "abdominal" in t:
        return ["Gastroenteritis", "Functional abdominal pain", "Other GI causes (rule out)"]

    if "headache" in t:
        return ["Tension-type headache", "Migraine", "Viral illness"]

    return ["Viral or mild illness", "Condition to be assessed by clinician"]


def _build_explanation(t: str, symptoms: list, severity_score: int, precautions: list):

    s = ", ".join(symptoms)

    line1 = f"Based on your description, we detected symptoms such as: {s}."

    line2 = f"The assessed severity score is {severity_score}/10."

    line3 = "This is not a diagnosis—it is guidance to help you decide when to seek care."

    line4 = "Recommended next steps include: " + "; ".join(precautions[:2]) + "."

    line5 = "If you feel worse at any time, seek in-person or emergency care as needed."

    return " ".join([line1, line2, line3, line4, line5])


def _estimate_confidence(
    t: str,
    symptoms: list,
    severity_score: int = None,
    followup_count: int = 0,
    is_followup: bool = False,
):

    real_symptoms = [
        s for s in (symptoms or [])
        if (s or "").strip().lower() != GENERAL_SYMPTOM_PLACEHOLDER.lower()
    ]

    score = 0.42

    if len((t or "").strip()) >= 20:
        score += 0.08
    if len((t or "").strip()) >= 60:
        score += 0.08

    if len(real_symptoms) >= 1:
        score += 0.10
    if len(real_symptoms) >= 2:
        score += 0.08
    if len(real_symptoms) >= 3:
        score += 0.06

    if severity_score is not None:
        if severity_score >= 8:
            score += 0.10
        elif severity_score >= 5:
            score += 0.07
        elif severity_score >= 3:
            score += 0.04

    score += min(followup_count, 3) * 0.05

    if is_followup:
        score -= 0.10

    return max(0.45, min(0.96, round(score, 2)))


def _build_reasoning(
    symptoms: list,
    severity_score: int,
    possible_conditions: list,
    urgency_level: str,
    followup_count: int = 0,
):

    symptom_text = ", ".join(symptoms[:5]) if symptoms else "general symptoms"
    condition_names = []
    for condition in possible_conditions[:3]:
        if isinstance(condition, dict):
            name = condition.get("condition")
        else:
            name = str(condition)
        if name:
            condition_names.append(name)

    reasoning_parts = [
        f"The assessment used the reported symptoms: {symptom_text}.",
        f"These symptoms produced a severity score of {severity_score}/10 and an urgency level of {urgency_level}.",
    ]

    if condition_names:
        reasoning_parts.append(
            "The most relevant condition patterns considered were "
            + ", ".join(condition_names)
            + "."
        )

    if followup_count > 0:
        reasoning_parts.append(
            "Earlier follow-up answers were also considered to reduce ambiguity in the triage result."
        )

    reasoning_parts.append(
        "This is a pattern-based safety assessment, not a confirmed diagnosis."
    )

    return " ".join(reasoning_parts)


MAX_FOLLOWUP_QUESTIONS = 3

from hygionx_medical_triage import HygionXMediAITriage

# Initialize the HygionX MediAI Triage system
hygionx_triage = HygionXMediAITriage()

def run_triage_pipeline(
    text: str,
    known_conditions: str = None,
    session_id: int = None,
    previous_symptoms: list = None,
    previous_messages: list = None,
    followup_count: int = 0,
    force_triage: bool = False,
) -> dict:
    """
    Enhanced triage pipeline using HygionX MediAI Triage system.
    Maintains backward compatibility with existing API while adding new features.
    """
    
    # Create a fresh instance for each request to avoid session contamination
    triage_instance = HygionXMediAITriage()
    
    # Initialize HygionX session with previous symptoms
    if previous_symptoms:
        triage_instance.session_symptoms = previous_symptoms.copy()
    triage_instance.follow_up_count = followup_count
    
    # Process the message through HygionX system
    response = triage_instance.process_message(text)
    
    # Convert HygionX response to existing format for compatibility
    if response['status'] == 'follow_up_needed':
        # Convert to existing followup format
        questions = [response['follow_up_question']]
        confidence = _estimate_confidence(
            text,
            response.get('total_symptoms', []),
            followup_count=response.get('follow_up_count', followup_count),
            is_followup=True,
        )
        return {
            "type": "followup", 
            "questions": questions, 
            "symptoms": response['total_symptoms'],
            "followup_count": response['follow_up_count'],
            "response_type": "question",
            "urgency": "low",
            "confidence": confidence,
            "reasoning": (
                "More detail is needed before making a final assessment. "
                f"Current symptom clues: {', '.join(response.get('total_symptoms', [])[:4]) or 'limited symptom detail'}."
            ),
        }
    else:
        # Convert to existing triage/emergency format
        assessment = response['final_assessment']['AI Assessment']
        
        # Determine response type based on urgency
        urgency_level = assessment['Urgency Level']
        response_type = "emergency" if urgency_level == "Emergency" else "triage"
        
        # Parse possible conditions to extract just the condition names
        possible_conditions = assessment.get('Possible Conditions', [])
        condition_names = [cond['condition'] for cond in possible_conditions]
        severity_score = assessment['Severity Score']
        confidence = _estimate_confidence(
            text,
            response.get('total_symptoms', []),
            severity_score=severity_score,
            followup_count=response.get('follow_up_count', followup_count),
        )
        reasoning = _build_reasoning(
            response.get('total_symptoms', []),
            severity_score,
            possible_conditions,
            urgency_level,
            followup_count=response.get('follow_up_count', followup_count),
        )
        
        # Build response in existing format
        result = {
            "type": response_type,
            "symptoms": response['total_symptoms'],
            "severity_score": severity_score,
            "urgency_level": urgency_level,
            "possible_conditions": [
                f"{cond['condition']} — {cond['probability']}" 
                for cond in possible_conditions
            ],
            "recommended_action": assessment['Recommended Action'],
            "explanation": assessment['Assessment'],
            "safety_notice": assessment['Safety Notice'],
            "followup_count": response['follow_up_count'],
            "response_type": "final"
        }
        result["possible_conditions_structured"] = possible_conditions
        result["possible_diseases"] = condition_names
        
        # Add emergency-specific fields if needed
        if response_type == "emergency":
            result["message"] = assessment['Recommended Action']
        
        # Add additional fields for compatibility
        result["severity"] = severity_score
        result["confidence"] = confidence
        result["reasoning"] = reasoning
        
        return result
