"""
Load and expose ML models for symptom extraction.
Call load_models() once at startup to preload SciSpaCy, MiniLM, FAISS, and datasets.
"""

import os
from pathlib import Path

# Globals populated by load_models()
nlp = None
embedder = None
index = None
symptom_list = []
severity_dict = {}
redflag_dict = {}
synonym_dict = {}

_models_loaded = False


def load_models(datasets_dir: str = None) -> bool:
    """
    Load SciSpaCy, SentenceTransformer, FAISS index, and dataset CSVs.
    Stores them in module globals. Safe to call multiple times (loads only once).
    Returns True if loading succeeded, False otherwise.
    """
    global nlp, embedder, index, symptom_list, severity_dict, redflag_dict, synonym_dict, _models_loaded

    if _models_loaded:
        return True

    base = Path(__file__).resolve().parent
    datasets_path = Path(datasets_dir) if datasets_dir else base / "Datasets"

    try:
        import spacy
        import faiss
        import numpy as np
        import pandas as pd
        from sentence_transformers import SentenceTransformer
        from negspacy.negation import Negex
    except ImportError as e:
        print(f"Warning: Missing dependency for ML models: {e}")
        return False

    try:
        print("Loading models...")

        # SciSpaCy
        nlp = spacy.load("en_ner_bc5cdr_md")
        nlp.add_pipe("negex", last=True)

        # SentenceTransformer
        embedder = SentenceTransformer("all-MiniLM-L6-v2")

        # Symptom dataset
        severity_csv = datasets_path / "Symptom_severity_dataset.csv"
        if not severity_csv.is_file():
            print(f"Warning: Dataset not found: {severity_csv}")
            return False

        symptom_df = pd.read_csv(severity_csv)
        symptom_df = symptom_df.drop_duplicates(subset="symptom")
        symptom_list = symptom_df["symptom"].str.lower().tolist()

        severity_dict = dict(
            zip(symptom_df["symptom"].str.lower(), symptom_df["weight"])
        )
        redflag_dict = dict(
            zip(symptom_df["symptom"].str.lower(), symptom_df["red_flag"])
        )

        # Synonym dataset
        synonym_csv = datasets_path / "symptom_synonyms.csv"
        if not synonym_csv.is_file():
            print(f"Warning: Synonym dataset not found: {synonym_csv}")
            synonym_dict = {}
        else:
            synonym_df = pd.read_csv(synonym_csv)
            synonym_dict = {}
            for _, row in synonym_df.iterrows():
                symptom = row["symptom"].lower()
                synonyms = row["synonyms"].split("|")
                for syn in synonyms:
                    synonym_dict[syn.strip().lower()] = symptom

        # Embeddings and FAISS
        print("Creating symptom embeddings...")
        symptom_embeddings = embedder.encode(symptom_list)
        symptom_embeddings = np.array(symptom_embeddings).astype("float32")

        dimension = symptom_embeddings.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(symptom_embeddings)

        print("Models loaded successfully")
        _models_loaded = True
        return True

    except Exception as e:
        print(f"Warning: Failed to load ML models: {e}")
        nlp = None
        embedder = None
        index = None
        symptom_list = []
        severity_dict = {}
        redflag_dict = {}
        synonym_dict = {}
        return False


def models_loaded() -> bool:
    """Return True if load_models() has completed successfully."""
    return _models_loaded
