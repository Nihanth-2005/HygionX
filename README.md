# HygionX MediAI Triage System

**Tagline: Bridging Artificial Intelligence and Explainable Medicine**

An AI-powered medical symptom assessment assistant that helps evaluate symptoms and provide appropriate medical guidance.

## Features

- **Symptom Extraction**: Automatically identifies symptoms from user messages
- **Session Management**: Maintains symptom history across the conversation
- **Follow-up Questions**: Asks clarifying questions when more information is needed
- **Severity Scoring**: Calculates risk level from 1-10 based on all symptoms
- **Emergency Detection**: Immediate emergency classification for critical symptoms
- **Condition Analysis**: Suggests possible medical conditions with probability scores
- **Safety-First Approach**: Always includes safety disclaimers and recommends professional medical care

## How It Works

### Session Symptom Rule
- Maintains a list called `SESSION_SYMPTOMS` across the entire conversation
- Considers ALL symptoms when generating final assessment
- Never ignores or removes symptoms unless explicitly resolved by user

### Follow-up Rule
- Asks follow-up questions when follow-up_count < 3 and symptom information is insufficient
- Questions are simple, preferably yes/no format
- Helps detect additional symptoms

### Final Triage Rule
- Generates final assessment when follow-up_count ≥ 3 OR sufficient symptoms are available
- Uses the FULL SESSION_SYMPTOMS list for comprehensive analysis

### Severity Scoring
- **1-3**: Low Risk
- **4-6**: Moderate Risk  
- **7-8**: High Risk
- **9-10**: Emergency

### Emergency Override
Immediate emergency classification if symptoms include:
- Severe chest pain
- Breathing difficulty
- Stroke symptoms
- Severe bleeding
- Loss of consciousness

## Files

- `hygionx_medical_triage.py` - Main triage system implementation
- `demo_triage.py` - Interactive demo for testing the system
- `README.md` - This documentation file

## Usage

### Running the Interactive Demo

```bash
python demo_triage.py
```

### Using the System Programmatically

```python
from hygionx_medical_triage import HygionXMediAITriage

# Initialize the system
triage = HygionXMediAITriage()

# Process user messages
response = triage.process_message("I have a headache and feel dizzy")

# Check if follow-up is needed
if response['status'] == 'follow_up_needed':
    print(triage.get_follow_up_question())
else:
    assessment = response['final_assessment']
    print(assessment)
```

## Example Conversation

```
User: I have a headache and feel dizzy
AI: I detected these symptoms: headache, dizziness
Total symptoms so far: headache, dizziness
AI: Do you also have fever, nausea, or dizziness?

User: Yes, I also have some nausea
AI: I detected these symptoms: nausea
Total symptoms so far: headache, dizziness, nausea

[Final Assessment Generated]
```

## Output Format

The final assessment includes:

- **Assessment**: Explanation of possible medical concerns
- **Severity Score**: Score from 1-10 based on combined symptom severity
- **Urgency Level**: Low Risk, Moderate Risk, High Risk, or Emergency
- **Recommended Action**: Clear medical guidance appropriate to urgency level
- **Possible Conditions**: Three possible conditions with probability percentages
- **Safety Notice**: Disclaimer about AI guidance vs professional medical diagnosis

## Safety Notice

⚠️ **IMPORTANT**: This AI provides guidance only and is not a substitute for professional medical diagnosis, treatment, or advice. Always consult with qualified healthcare professionals for medical concerns, especially in emergency situations.

## Technical Details

- **Language**: Python 3.x
- **Dependencies**: Standard library only (re, json, typing, datetime)
- **Architecture**: Object-oriented design with clear separation of concerns
- **Pattern Matching**: Uses regex patterns for symptom extraction
- **State Management**: Maintains conversation state across multiple messages

## Contributing

When modifying the system:
1. Maintain the emergency override rule as the highest priority
2. Ensure all symptoms in SESSION_SYMPTOMS are considered in assessments
3. Keep follow-up questions simple and focused
4. Preserve the safety-first approach in all outputs

## License

This system is designed for educational and research purposes. Medical AI systems should always be developed and deployed with appropriate clinical validation and regulatory compliance.
