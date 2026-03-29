import re
import json
from typing import List, Dict, Tuple
from datetime import datetime

from model_loader import (
    nlp,
    embedder,
    index,
    symptom_list,
    severity_dict,
    synonym_dict,
    redflag_dict,
    models_loaded,
)

class HygionXMediAITriage:
    """
    HygionX MediAI Triage - AI Medical Symptom Assessment Assistant
    Tagline: Bridging Artificial Intelligence and Explainable Medicine
    """
    
    def __init__(self):
        self.session_symptoms = []
        self.follow_up_count = 0
        self.max_follow_ups = 3
        self.ml_enabled = models_loaded() and all([
            nlp is not None,
            embedder is not None,
            index is not None,
            symptom_list,
        ])
        
        # Emergency symptoms that trigger immediate emergency classification
        self.emergency_symptoms = [
            "severe chest pain", "chest pain", "breathing difficulty", 
            "difficulty breathing", "shortness of breath", "breathlessness", "stroke symptoms",
            "severe bleeding", "loss of consciousness", "fainting", "unconscious"
        ]
        
        # Common symptom patterns for extraction. Values are normalized symptom labels.
        self.symptom_patterns = {
            r'\b(headache|migraine|head ache)\b': 'headache',
            r'\b(fever|temperature|chills|high temperature)\b': 'fever',
            r'\b(cough|coughing)\b': 'cough',
            r'\b(cold|runny nose|blocked nose|nasal congestion|congestion)\b': 'cold',
            r'\b(sore throat|throat pain)\b': 'sore throat',
            r'\b(nausea)\b': 'nausea',
            r'\b(vomiting|vomit)\b': 'vomiting',
            r'\b(dizziness|lightheaded|lightheadedness|vertigo)\b': 'dizziness',
            r'\b(fatigue|tiredness|tired|weakness)\b': 'fatigue',
            r'\b(pain|ache|discomfort)\b': 'pain',
            r'\b(swelling|inflammation)\b': 'swelling',
            r'\b(rash|itching|itchy)\b': 'rash',
            r'\b(shortness of breath|short of breath|breathlessness|breathing difficulty|difficulty breathing)\b': 'shortness of breath',
            r'\b(chest pain|chest tightness)\b': 'chest pain',
            r'\b(stomach pain|abdominal pain|stomach ache|abdominal discomfort)\b': 'stomach pain',
            r'\b(diarrhea|constipation)\b': 'diarrhea',
            r'\b(insomnia|sleep|sleeping|sleeplessness)\b': 'sleep changes',
            r'\b(appetite loss|loss of appetite|poor appetite)\b': 'appetite changes',
            r'\b(anxiety|stress)\b': 'anxiety',
        }
        
        # Follow-up question templates
        self.follow_up_questions = [
            "Do you also have fever, nausea, or dizziness?",
            "Are you experiencing any pain or discomfort?",
            "Have you noticed any changes in your appetite or sleep?",
            "Do you have any difficulty breathing or chest tightness?",
            "Are you feeling more tired than usual?",
            "Have you experienced any recent injuries or falls?"
        ]

    def _normalize_text(self, text: str) -> str:
        text = (text or "").lower()

        for syn, symptom in synonym_dict.items():
            pattern = r"\b" + re.escape(syn) + r"\b"
            text = re.sub(pattern, symptom, text)

        return text

    def _extract_scispacy(self, text: str) -> List[str]:
        if not self.ml_enabled:
            return []

        doc = nlp(text)
        symptoms = []

        for ent in doc.ents:
            if not ent._.negex:
                value = ent.text.lower().strip()
                if value and value not in symptoms:
                    symptoms.append(value)

        return symptoms

    def _extract_minilm(self, text: str, scispacy_symptoms: List[str], threshold: float = 0.72) -> List[str]:
        if not self.ml_enabled:
            return []

        phrases = re.split(r",|and|with|but|;", text)
        phrases = [p.strip() for p in phrases if len(p.strip()) > 2]
        recovered = []

        for phrase in phrases:
            query_embedding = embedder.encode([phrase]).astype("float32")
            distances, indices = index.search(query_embedding, 1)

            similarity = 1 / (1 + distances[0][0])
            matched_symptom = symptom_list[indices[0][0]]

            if similarity >= threshold and matched_symptom not in scispacy_symptoms and matched_symptom not in recovered:
                recovered.append(matched_symptom)

        return recovered

    def _merge_symptoms(self, scispacy_symptoms: List[str], minilm_symptoms: List[str]) -> List[str]:
        return list(set([s.strip() for s in (scispacy_symptoms + minilm_symptoms) if s and s.strip()]))

    def _remove_duplicate_symptoms(self, symptoms: List[str]) -> List[str]:
        symptoms = list(set(symptoms))
        cleaned = []

        for s1 in symptoms:
            keep = True
            for s2 in symptoms:
                if s1 != s2 and len(s1) < len(s2) and s1 in s2:
                    keep = False
                    break

            if keep:
                cleaned.append(s1)

        return cleaned

    def _remove_negated_symptoms(self, text: str, symptoms: List[str]) -> List[str]:
        if not self.ml_enabled:
            return symptoms

        doc = nlp(text)
        negated_entities = set()

        for ent in doc.ents:
            if ent._.negex:
                negated_entities.add(ent.text.lower())

        return [symptom for symptom in symptoms if symptom not in negated_entities]

    def _extract_symptoms_fallback(self, text: str) -> List[str]:
        """Fallback extractor used when the ML symptom pipeline is unavailable."""
        text_lower = text.lower()
        found_symptoms = []
        
        for pattern, label in self.symptom_patterns.items():
            if re.search(pattern, text_lower) and label not in found_symptoms:
                found_symptoms.append(label)
        
        # Check for emergency symptoms
        for emergency in self.emergency_symptoms:
            if emergency in text_lower and emergency not in found_symptoms:
                found_symptoms.append(emergency)
        
        return found_symptoms

    def extract_symptoms(self, text: str) -> List[str]:
        """Extract symptoms using the same staged flow as symptom_extraction_pipeline."""
        if not text:
            return []

        if self.ml_enabled:
            normalized_text = self._normalize_text(text)
            scispacy_symptoms = self._extract_scispacy(normalized_text)
            minilm_symptoms = self._extract_minilm(normalized_text, scispacy_symptoms)
            final_symptoms = self._merge_symptoms(scispacy_symptoms, minilm_symptoms)
            final_symptoms = self._remove_duplicate_symptoms(final_symptoms)
            final_symptoms = self._remove_negated_symptoms(normalized_text, final_symptoms)

            if final_symptoms:
                return final_symptoms

        return self._extract_symptoms_fallback(text)
    
    def add_symptoms(self, user_message: str) -> List[str]:
        """Add new symptoms from user message to SESSION_SYMPTOMS."""
        new_symptoms = self.extract_symptoms(user_message)
        
        for symptom in new_symptoms:
            if symptom not in self.session_symptoms:
                self.session_symptoms.append(symptom)
        
        return new_symptoms
    
    def is_emergency(self) -> bool:
        """Check if any emergency symptoms are present."""
        if any(emergency in self.session_symptoms for emergency in self.emergency_symptoms):
            return True

        return any(redflag_dict.get(symptom) == "yes" for symptom in self.session_symptoms)
    
    def calculate_severity_score(self) -> int:
        """Calculate severity score from 1-10 based on all symptoms."""
        if self.is_emergency():
            return 10

        if self.ml_enabled and self.session_symptoms:
            total_score = sum(int(severity_dict.get(symptom, 0) or 0) for symptom in self.session_symptoms)
            if total_score <= 0:
                return 1
            return min(10, max(1, total_score))
        
        base_score = 0
        
        # Scoring based on symptom count and type
        symptom_count = len(self.session_symptoms)
        
        if symptom_count == 0:
            return 1
        elif symptom_count == 1:
            base_score = 2
        elif symptom_count == 2:
            base_score = 4
        elif symptom_count == 3:
            base_score = 6
        elif symptom_count == 4:
            base_score = 7
        else:
            base_score = 8
        
        # Add points for specific severe symptoms
        severe_symptoms = ['severe', 'acute', 'intense', 'unbearable']
        for symptom in self.session_symptoms:
            if any(severe in symptom for severe in severe_symptoms):
                base_score = min(base_score + 2, 9)
        
        return min(base_score, 10)
    
    def get_urgency_level(self, severity_score: int) -> str:
        """Determine urgency level based on severity score."""
        if self.is_emergency():
            return "Emergency"
        elif severity_score >= 7:
            return "High Risk"
        elif severity_score >= 4:
            return "Moderate Risk"
        else:
            return "Low Risk"
    
    def get_recommended_action(self, urgency: str) -> str:
        """Provide clear medical guidance appropriate to urgency level."""
        actions = {
            "Emergency": "Seek immediate emergency medical care by calling emergency services or going to the nearest emergency department right away. Do not wait or drive yourself. If someone is with you, have them stay with you until help arrives.",
            "High Risk": "Seek urgent medical attention within the next few hours by visiting an urgent care clinic or emergency department. Avoid strenuous activity and have someone monitor your condition if possible.",
            "Moderate Risk": "Schedule a medical appointment within 24-48 hours for proper evaluation. Rest and stay hydrated while monitoring for any changes in your symptoms.",
            "Low Risk": "Monitor symptoms at home with rest and hydration. Over-the-counter medications may help if used according to label instructions. Seek medical care if symptoms persist or worsen."
        }
        return actions.get(urgency, "Consult with a healthcare professional for proper evaluation and treatment.")
    
    def generate_possible_conditions(self) -> List[Dict[str, str]]:
        """Generate possible conditions based on symptoms."""
        conditions = []
        
        # Simple condition mapping based on symptoms
        symptom_conditions = {
            'headache': ['Migraine', 'Tension Headache', 'Sinus Infection'],
            'fever': ['Flu', 'COVID-19', 'Common Cold'],
            'cough': ['Bronchitis', 'Pneumonia', 'Common Cold'],
            'nausea': ['Gastroenteritis', 'Food Poisoning', 'Migraine'],
            'chest pain': ['Heart Attack', 'Angina', 'Costochondritis'],
            'breathing difficulty': ['Asthma', 'Pneumonia', 'Anxiety Attack'],
            'dizziness': ['Vertigo', 'Dehydration', 'Low Blood Pressure']
        }
        
        # Find matching conditions based on symptoms
        matching_conditions = {}
        for symptom in self.session_symptoms:
            for key in symptom_conditions:
                if key in symptom:
                    for condition in symptom_conditions[key]:
                        matching_conditions[condition] = matching_conditions.get(condition, 0) + 1
        
        if not matching_conditions:
            # Default conditions if no specific matches
            conditions = [
                {"condition": "Viral Infection", "probability": "40%"},
                {"condition": "Stress-Related Symptoms", "probability": "35%"},
                {"condition": "Minor Illness", "probability": "25%"}
            ]
        else:
            # Sort by frequency and assign probabilities
            sorted_conditions = sorted(matching_conditions.items(), key=lambda x: x[1], reverse=True)
            total = sum(matching_conditions.values())
            
            for i, (condition, count) in enumerate(sorted_conditions[:3]):
                if i == 0:
                    prob = max(50, int((count / total) * 100))
                elif i == 1:
                    prob = max(30, int((count / total) * 100))
                else:
                    # Calculate remaining probability for third condition
                    existing_prob = sum(int(c["probability"].rstrip('%')) for c in conditions) if conditions else 0
                    prob = max(20, 100 - existing_prob)
                
                conditions.append({"condition": condition, "probability": f"{prob}%"})
        
        # Ensure probabilities sum to 100%
        if len(conditions) == 3:
            current_sum = sum(int(c["probability"].rstrip('%')) for c in conditions)
            if current_sum != 100:
                diff = 100 - current_sum
                conditions[0]["probability"] = f"{int(conditions[0]['probability'].rstrip('%')) + diff}%"
        elif len(conditions) == 2:
            # Ensure 2 conditions sum to 100%
            current_sum = sum(int(c["probability"].rstrip('%')) for c in conditions)
            if current_sum != 100:
                diff = 100 - current_sum
                conditions[0]["probability"] = f"{int(conditions[0]['probability'].rstrip('%')) + diff}%"
        elif len(conditions) == 1:
            conditions[0]["probability"] = "100%"
        
        return conditions
    
    def should_ask_follow_up(self) -> bool:
        """Determine if a follow-up question should be asked."""
        return (self.follow_up_count < self.max_follow_ups and 
                len(self.session_symptoms) < 2)
    
    def get_follow_up_question(self) -> str:
        """Get a follow-up question to clarify symptoms."""
        if self.follow_up_count < len(self.follow_up_questions):
            question = self.follow_up_questions[self.follow_up_count]
            self.follow_up_count += 1
            return question
        else:
            return "Can you describe your symptoms in more detail?"
    
    def generate_final_assessment(self) -> Dict:
        """Generate the final AI assessment."""
        severity_score = self.calculate_severity_score()
        urgency_level = self.get_urgency_level(severity_score)
        
        # Generate detailed assessment explanation (3-5 sentences)
        symptoms_str = ', '.join(self.session_symptoms)
        
        # Build detailed explanation based on symptoms and severity
        if len(self.session_symptoms) == 1:
            explanation = f"Based on the symptoms detected in this session: {symptoms_str}. This single symptom may indicate various medical conditions ranging from mild to serious depending on severity and duration. "
        elif len(self.session_symptoms) == 2:
            explanation = f"Based on the symptoms detected in this session: {symptoms_str}. This combination of symptoms suggests a systemic illness that may be affecting multiple body systems. "
        else:
            explanation = f"Based on the symptoms detected in this session: {symptoms_str}. This combination of multiple symptoms indicates a more complex medical condition that requires careful evaluation. "
        
        # Add medical context and urgency reasoning
        explanation += f"The severity score of {severity_score}/10 was assigned based on the number and type of symptoms present. "
        
        # Add monitoring guidance
        if urgency_level == "Emergency":
            explanation += "These symptoms require immediate medical attention due to their potential seriousness. "
        elif urgency_level == "High Risk":
            explanation += "These symptoms should be evaluated urgently due to their potential to worsen. "
        elif urgency_level == "Moderate Risk":
            explanation += "These symptoms warrant medical attention within 24-48 hours. "
        else:
            explanation += "These symptoms can often be managed at home with monitoring. "
        
        explanation += "Professional medical evaluation is recommended for proper diagnosis and treatment."
        
        assessment = {
            "AI Assessment": {
                "Assessment": explanation,
                "Severity Score": severity_score,
                "Urgency Level": urgency_level,
                "Recommended Action": self.get_recommended_action(urgency_level),
                "Possible Conditions": self.generate_possible_conditions(),
                "Safety Notice": "This AI provides guidance only and is not a substitute for professional medical diagnosis."
            },
            "Session Data": {
                "Session Symptoms": self.session_symptoms,
                "Follow-up Count": self.follow_up_count,
                "Timestamp": datetime.now().isoformat()
            }
        }
        
        return assessment
    
    def process_message(self, user_message: str) -> Dict:
        """Process user message and generate appropriate response."""
        # Add symptoms from message
        new_symptoms = self.add_symptoms(user_message)
        
        response = {
            "new_symptoms_detected": new_symptoms,
            "total_symptoms": self.session_symptoms,
            "follow_up_count": self.follow_up_count
        }
        
        # Determine if we should ask follow-up or generate final assessment
        if self.should_ask_follow_up():
            response["follow_up_question"] = self.get_follow_up_question()
            response["status"] = "follow_up_needed"
        else:
            response["final_assessment"] = self.generate_final_assessment()
            response["status"] = "assessment_complete"
        
        return response
    
    def reset_session(self):
        """Reset the session for a new patient."""
        self.session_symptoms = []
        self.follow_up_count = 0


# Example usage
if __name__ == "__main__":
    triage = HygionXMediAITriage()
    
    print("HygionX MediAI Triage System")
    print("Tagline: Bridging Artificial Intelligence and Explainable Medicine")
    print("=" * 60)
    
    # Simulate a conversation
    messages = [
        "I have a headache and feel dizzy",
        "Yes, I also have some nausea",
        "No chest pain or breathing issues"
    ]
    
    for i, message in enumerate(messages, 1):
        print(f"\nUser Message {i}: {message}")
        response = triage.process_message(message)
        
        print(f"New Symptoms: {response['new_symptoms_detected']}")
        print(f"Total Symptoms: {response['total_symptoms']}")
        
        if response['status'] == 'follow_up_needed':
            print(f"Follow-up Question: {response['follow_up_question']}")
        else:
            print("\n" + "=" * 60)
            print("FINAL AI ASSESSMENT")
            print("=" * 60)
            assessment = response['final_assessment']['AI Assessment']
            
            print(f"\nAssessment")
            print(assessment['Assessment'])
            
            print(f"\nSeverity Score")
            print(assessment['Severity Score'])
            
            print(f"\nUrgency Level")
            print(assessment['Urgency Level'])
            
            print(f"\nRecommended Action")
            print(assessment['Recommended Action'])
            
            print(f"\nPossible Conditions")
            for condition in assessment['Possible Conditions']:
                print(f"- {condition['condition']}: {condition['probability']}")
            
            print(f"\nSafety Notice")
            print(assessment['Safety Notice'])
