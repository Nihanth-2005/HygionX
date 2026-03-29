from hygionx_medical_triage import HygionXMediAITriage

def interactive_demo():
    """Interactive demo of the HygionX MediAI Triage system."""
    
    triage = HygionXMediAITriage()
    
    print("\n" + "=" * 60)
    print("HygionX MediAI Triage System")
    print("Tagline: Bridging Artificial Intelligence and Explainable Medicine")
    print("=" * 60)
    print("\nPlease describe your symptoms. Type 'quit' to exit.")
    print("-" * 60)
    
    while True:
        user_input = input("\nYou: ").strip()
        
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("\nThank you for using HygionX MediAI Triage. Take care!")
            break
        
        if not user_input:
            continue
        
        # Process the message
        response = triage.process_message(user_input)
        
        print(f"\nAI: I detected these symptoms: {', '.join(response['new_symptoms_detected'])}")
        print(f"Total symptoms so far: {', '.join(response['total_symptoms'])}")
        
        if response['status'] == 'follow_up_needed':
            print(f"\nAI: {response['follow_up_question']}")
        else:
            print("\n" + "=" * 60)
            print("FINAL AI ASSESSMENT")
            print("=" * 60)
            
            assessment = response['final_assessment']['AI Assessment']
            
            print(f"\nAssessment")
            print(assessment['Assessment'])
            
            print(f"\nSeverity Score")
            print(f"{assessment['Severity Score']}/10")
            
            print(f"\nUrgency Level")
            print(assessment['Urgency Level'])
            
            print(f"\nRecommended Action")
            print(assessment['Recommended Action'])
            
            print(f"\nPossible Conditions")
            for condition in assessment['Possible Conditions']:
                print(f"- {condition['condition']}: {condition['probability']}")
            
            print(f"\nSafety Notice")
            print(assessment['Safety Notice'])
            
            print("\n" + "=" * 60)
            print("Assessment complete. Thank you for using HygionX MediAI Triage.")
            break

if __name__ == "__main__":
    interactive_demo()
