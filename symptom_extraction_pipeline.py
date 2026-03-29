import re
from model_loader import (
    nlp,
    embedder,
    index,
    symptom_list,
    severity_dict,
    synonym_dict,
    redflag_dict
)

# -----------------------------
# STEP 0 — Normalize Synonyms
# -----------------------------
def normalize_text(text):

    text = text.lower()

    for syn, symptom in synonym_dict.items():

        pattern = r"\b" + re.escape(syn) + r"\b"

        text = re.sub(pattern, symptom, text)

    return text


# -----------------------------
# STEP 1 — SciSpaCy Extraction
# -----------------------------
def extract_scispacy(text):

    doc = nlp(text)

    symptoms = []

    for ent in doc.ents:

        if not ent._.negex:
            symptoms.append(ent.text.lower())

    return symptoms


# -----------------------------
# STEP 2 — MiniLM Recovery
# -----------------------------
def extract_minilm(text, scispacy_symptoms, threshold=0.72):   # raised threshold

    phrases = re.split(r",|and|with|but|;", text)

    phrases = [p.strip() for p in phrases if len(p.strip()) > 2]

    recovered = []

    for phrase in phrases:

        query_embedding = embedder.encode([phrase]).astype("float32")

        distances, indices = index.search(query_embedding, 1)

        similarity = 1 / (1 + distances[0][0])

        matched_symptom = symptom_list[indices[0][0]]

        if similarity >= threshold:

            if matched_symptom not in scispacy_symptoms:
                recovered.append(matched_symptom)

    return recovered


# -----------------------------
# STEP 3 — Merge Symptoms
# -----------------------------
def merge_symptoms(scispacy_symptoms, minilm_symptoms):

    combined = scispacy_symptoms + minilm_symptoms

    combined = list(set([s.strip() for s in combined]))

    return combined


# -----------------------------
# STEP 4 — Remove Duplicate / Hierarchical Symptoms
# -----------------------------
def remove_duplicate_symptoms(symptoms):

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


# -----------------------------
# STEP 5 — Remove Negated Symptoms
# -----------------------------
def remove_negated_symptoms(text, symptoms):

    doc = nlp(text)

    negated_entities = set()

    for ent in doc.ents:
        if ent._.negex:
            negated_entities.add(ent.text.lower())

    cleaned = []

    for symptom in symptoms:

        if symptom not in negated_entities:
            cleaned.append(symptom)

    return cleaned


# -----------------------------
# STEP 6 — Severity Calculation
# -----------------------------
def calculate_severity(symptoms):

    symptom_scores = {}

    total_score = 0

    red_flags = []

    for symptom in symptoms:

        score = severity_dict.get(symptom, 0)

        symptom_scores[symptom] = score

        total_score += score

        if redflag_dict.get(symptom) == "yes":
            red_flags.append(symptom)

    return symptom_scores, total_score, red_flags


# -----------------------------
# FINAL PIPELINE
# -----------------------------
def extract_symptoms(text):

    # Step 0 — Normalize synonyms
    text = normalize_text(text)

    # Step 1 — SciSpaCy extraction
    scispacy_symptoms = extract_scispacy(text)

    # Step 2 — MiniLM recovery
    minilm_symptoms = extract_minilm(text, scispacy_symptoms)

    # Step 3 — Merge
    final_symptoms = merge_symptoms(scispacy_symptoms, minilm_symptoms)

    # Step 4 — Remove hierarchical duplicates
    final_symptoms = remove_duplicate_symptoms(final_symptoms)

    # Step 5 — Remove negated symptoms
    final_symptoms = remove_negated_symptoms(text, final_symptoms)

    # Step 6 — Severity scoring
    severity_scores, total_score, red_flags = calculate_severity(final_symptoms)

    return {
        "symptoms": final_symptoms,
        "severity_scores": severity_scores,
        "total_severity": total_score,
        "red_flags": red_flags
    }