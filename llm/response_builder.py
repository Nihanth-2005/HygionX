import os, sys
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)
from llm.llm_client import call_llm
import json
import re


def clean_llm_response(text):
    """
    Clean LLM response to extract valid JSON by removing reasoning blocks and extra text.
    
    Args:
        text (str): Raw LLM response
        
    Returns:
        str: Cleaned JSON string ready for parsing
    """
    if not text:
        return "{}"
    
    clean_text = text.strip()
    
    # Remove reasoning blocks between <think> and </think>
    if "<think>" in clean_text and "</think>" in clean_text:
        # Remove content between reasoning tags
        clean_text = re.sub(r'<think>.*?</think>', '', clean_text, flags=re.DOTALL)
    
    # Find the first opening brace
    start_index = clean_text.find("{")
    if start_index == -1:
        return "{}"
    
    # Extract from first { to the end
    clean_text = clean_text[start_index:]
    
    # Find the last closing brace
    last_brace_index = clean_text.rfind("}")
    if last_brace_index == -1:
        return "{}"
    
    # Extract up to the last closing brace
    clean_text = clean_text[:last_brace_index + 1]
    
    return clean_text


def safe_json_parse(text, fallback_response=None):
    """
    Safely parse JSON with fallback response.
    
    Args:
        text (str): Text to parse as JSON
        fallback_response (dict): Fallback response if parsing fails
        
    Returns:
        dict: Parsed JSON or fallback response
    """
    if fallback_response is None:
        fallback_response = {
            "assessment_summary": "Based on the symptoms provided, further evaluation may be needed.",
            "recommended_action": "Monitor symptoms and consult a healthcare professional if symptoms worsen.",
            "follow_up_questions": [],
            "explanation": "The AI could not generate detailed reasoning due to formatting issues.",
            "safety_note": "This system provides guidance and is not a substitute for professional medical advice."
        }
    
    try:
        # Clean the response first
        clean_text = clean_llm_response(text)
        return json.loads(clean_text)
    except json.JSONDecodeError as e:
        print(f"JSON parsing failed after cleaning: {e}")
        print(f"Cleaned text: {clean_text}")
        return fallback_response
    except Exception as e:
        print(f"Unexpected error during JSON parsing: {e}")
        return fallback_response


# --------------------------------------------------
# Optimized LLM Response Generator
# --------------------------------------------------
def generate_structured_response(symptoms, urgency, predictions, confidence_score=0.5):
    """
    Generate structured AI response with assessment, urgency, recommendations, and follow-up questions
    Returns a structured response that can be easily parsed by the frontend
    """
    
    # Prepare context for LLM
    top_conditions = [disease for disease, score in predictions[:3]] if predictions else []
    confidence_percent = int(confidence_score * 100)
    
    # Determine if follow-up questions are needed
    needs_clarification = confidence_score < 0.7 or urgency == "moderate"
    
    system_prompt = """You are a medical AI triage assistant providing structured health guidance.

CRITICAL RULES:
1. NEVER provide definitive medical diagnoses
2. ALWAYS include a medical disclaimer
3. Use cautious, supportive language
4. Focus on assessment and guidance, not treatment
5. Generate 2-4 relevant follow-up questions when confidence is low or symptoms are vague

RESPONSE FORMAT (JSON):
{
    "assessment_summary": "Brief assessment of symptoms",
    "recommended_action": "Clear action guidance based on urgency",
    "follow_up_questions": ["question1", "question2", "question3"],
    "explanation": "Simple explanation of why this guidance is given",
    "safety_note": "Medical disclaimer"
}

IMPORTANT: Return ONLY valid JSON. Do not include reasoning, explanations outside JSON, markdown formatting, or <think> tags. The response must follow the schema exactly with no additional text."""

    user_prompt = f"""Patient Information:
- Symptoms described: {symptoms}
- Urgency level: {urgency}
- Confidence score: {confidence_percent}%
- Top possible conditions: {', '.join(top_conditions) if top_conditions else 'No specific conditions identified'}

Generate structured response following the JSON format above. Include follow-up questions if more information would be helpful for assessment."""

    try:
        # Call LLM with optimized parameters
        response = call_llm(system_prompt, user_prompt, temperature=0.3, max_tokens=300)
        
        if response:
            print(f"LLM response received: {response[:100]}...")
            # Use safe JSON parsing with fallback
            structured_data = safe_json_parse(response)
            print(f"JSON parsing successful: {list(structured_data.keys())}")
            return validate_and_enhance_response(structured_data, urgency, confidence_score)
        else:
            print("LLM returned empty response")
            return create_error_response(urgency)
            
    except Exception as e:
        print(f"Error in LLM response generation: {e}")
        return create_error_response(urgency)


def validate_and_enhance_response(response_data, urgency, confidence_score):
    """Validate and enhance the LLM response"""
    
    # Ensure required fields exist
    enhanced = response_data.copy()
    
    # Add default values for missing fields
    enhanced.setdefault('assessment_summary', 'Symptoms have been assessed.')
    enhanced.setdefault('recommended_action', get_default_action(urgency))
    enhanced.setdefault('follow_up_questions', [])
    enhanced.setdefault('explanation', 'Assessment based on symptom patterns and medical guidelines.')
    enhanced.setdefault('safety_note', 'This system provides health guidance and is not a substitute for professional medical diagnosis.')
    
    # Ensure follow-up questions are appropriate
    if confidence_score < 0.7 and not enhanced['follow_up_questions']:
        enhanced['follow_up_questions'] = get_default_followup_questions()
    
    return enhanced


def get_default_action(urgency):
    """Get default recommended action based on urgency"""
    actions = {
        'high': 'Seek immediate medical attention. Visit emergency department or call emergency services.',
        'moderate': 'Consult a healthcare professional within 24 hours for proper evaluation.',
        'low': 'Monitor symptoms and consult a doctor if they persist or worsen.'
    }
    return actions.get(urgency, actions['low'])


def get_default_followup_questions():
    """Get default follow-up questions for clarification"""
    return [
        "How long have you been experiencing these symptoms?",
        "Is the pain or discomfort getting worse?",
        "Do you have any other symptoms you haven't mentioned?"
    ]


def create_fallback_response(llm_response, urgency, confidence_score):
    """Create structured response from plain text LLM output"""
    return {
        'assessment_summary': llm_response[:200] + '...' if len(llm_response) > 200 else llm_response,
        'recommended_action': get_default_action(urgency),
        'follow_up_questions': get_default_followup_questions() if confidence_score < 0.7 else [],
        'explanation': 'Assessment based on described symptoms and clinical patterns.',
        'safety_note': 'This system provides health guidance and is not a substitute for professional medical diagnosis.'
    }


def create_error_response(urgency):
    """Create response when LLM fails"""
    return {
        'assessment_summary': 'I apologize, but I encountered an error processing your request. Please try again.',
        'recommended_action': get_default_action(urgency),
        'follow_up_questions': [],
        'explanation': 'System error occurred during assessment.',
        'safety_note': 'This system provides health guidance and is not a substitute for professional medical diagnosis.'
    }


# --------------------------------------------------
# Backward Compatibility Functions
# --------------------------------------------------
def generate_final_response(symptoms, urgency, predictions):
    """Legacy function for backward compatibility"""
    structured = generate_structured_response(symptoms, urgency, predictions)
    
    # Convert to simple text format for existing code
    response_parts = [
        structured['assessment_summary'],
        f"\nRecommended Action: {structured['recommended_action']}"
    ]
    
    if structured['follow_up_questions']:
        response_parts.append("\nFollow-up Questions:")
        for q in structured['follow_up_questions']:
            response_parts.append(f"• {q}")
    
    response_parts.append(f"\n{structured['safety_note']}")
    
    return '\n'.join(response_parts)


def generate_why_explanation(symptoms, urgency, predictions):
    """Enhanced explanation generator"""
    if urgency == "high":
        return "The system detected symptom patterns commonly associated with urgent medical conditions. Specific combinations of symptoms triggered emergency escalation rules to ensure your safety."

    if not predictions:
        return "The symptoms did not strongly match any high-risk or specific condition. This advice is based on general symptom monitoring and safety guidelines."

    top_condition = predictions[0][0]
    confidence = predictions[0][1] if predictions else 0
    
    explanation = f"This assessment is based on symptom patterns commonly seen in conditions such as {top_condition}. "
    explanation += f"The system analyzed your described symptoms with {int(confidence * 100)}% confidence and evaluated overall severity before generating guidance. "
    explanation += "Multiple AI models (ClinicalBERT for disease classification, MPNet for semantic matching, and a severity engine) contributed to this assessment."
    
    return explanation


# --------------------------------------------------
# Follow-up Question Generator
# --------------------------------------------------
def generate_clarification_questions(symptoms, urgency, confidence_score):
    """Generate specific clarification questions based on context"""
    
    if confidence_score >= 0.8:
        return []  # High confidence, no clarification needed
    
    # Analyze symptoms for context-aware questions
    symptoms_lower = symptoms.lower()
    context_questions = []
    
    # Fever-related questions
    if 'fever' in symptoms_lower or 'temperature' in symptoms_lower:
        context_questions.extend([
            "What is your exact temperature if you've measured it?",
            "Did the fever start suddenly or gradually?",
            "Are you experiencing chills or sweating with the fever?"
        ])
    
    # Headache-related questions
    if 'headache' in symptoms_lower:
        context_questions.extend([
            "Where exactly is the headache located (forehead, back of head, one side)?",
            "Is this the worst headache you've ever had?",
            "Does light or sound make the headache worse?",
            "Did the headache start suddenly or develop gradually?"
        ])
    
    # Pain-related questions
    if 'pain' in symptoms_lower:
        context_questions.extend([
            "Can you rate the pain on a scale of 1 to 10?",
            "Is the pain constant or does it come and go?",
            "Does anything make the pain better or worse?",
            "Did the pain start after any specific activity or injury?"
        ])
    
    # Cough-related questions
    if 'cough' in symptoms_lower:
        context_questions.extend([
            "Is the cough dry or productive (with phlegm)?",
            "Are you coughing up any colored phlegm?",
            "Does the cough worsen at night or when lying down?"
        ])
    
    # Stomach/GI-related questions
    if 'stomach' in symptoms_lower or 'abdominal' in symptoms_lower or 'nausea' in symptoms_lower:
        context_questions.extend([
            "Is the pain sharp, dull, or cramp-like?",
            "Have you had any changes in appetite or bowel movements?",
            "Does eating make the symptoms better or worse?"
        ])
    
    # Chest-related questions
    if 'chest' in symptoms_lower:
        context_questions.extend([
            "Do you have any shortness of breath with the chest symptoms?",
            "Does the pain spread to your arm, jaw, or back?",
            "Is the pain worse with deep breathing or movement?"
        ])
    
    # Time/duration questions
    context_questions.extend([
        "When exactly did these symptoms start?",
        "Have you had similar symptoms in the past?",
        "Are the symptoms getting worse, better, or staying the same?"
    ])
    
    # General follow-up questions
    general_questions = [
        "Have you taken any medications for these symptoms?",
        "Do you have any other medical conditions?",
        "Have you been in contact with anyone who's been sick recently?",
        "Have you traveled recently or been to any crowded places?"
    ]
    
    # Combine and return unique questions
    all_questions = context_questions + general_questions
    
    # Remove duplicates and return 4-6 most relevant questions
    unique_questions = []
    seen = set()
    for question in all_questions:
        if question not in seen:
            seen.add(question)
            unique_questions.append(question)
    
    return unique_questions[:6]