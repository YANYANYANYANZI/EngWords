#!/usr/bin/env python3
"""Initialize vocab JSON database from subclustered_words.xlsx."""
from pathlib import Path
import json
import pandas as pd
from datetime import datetime
from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
XLSX_PATH = BASE_DIR / "subclustered_words.xlsx"

COLUMN_WORD = "Column1"
COLUMN_TRANSLATION = "Column2"


def normalize_sheet_name(sheet_name: str) -> str:
    return sheet_name.strip()


def init_data() -> None:
    if not XLSX_PATH.exists():
        raise FileNotFoundError(f"Excel not found: {XLSX_PATH}")

    DATA_DIR.mkdir(exist_ok=True, parents=True)
    (DATA_DIR / "unit_summaries").mkdir(exist_ok=True, parents=True)

    xls = pd.ExcelFile(XLSX_PATH)
    unit_entries = []
    all_words = []

    for sheet_name in xls.sheet_names:
        normalized = normalize_sheet_name(sheet_name)
        df = pd.read_excel(XLSX_PATH, sheet_name=sheet_name)

        words = []
        for _, row in df.iterrows():
            word = row.get(COLUMN_WORD)
            translation = row.get(COLUMN_TRANSLATION)
            if pd.isna(word) or str(word).strip() == "":
                continue
            word_entry = {
                "word": str(word).strip(),
                "translation": str(translation).strip() if not pd.isna(translation) else "",
                "unit": normalized,
                "status": {
                    "memorized_past": False,
                    "memorized_today": False,
                    "last_reviewed": None,
                    "review_count": 0,
                },
                "notes": "",
                "pos": None,
                "definitions": [],
                "example_sentences": [],
            }
            words.append(word_entry)
            all_words.append(word_entry)

        file_path = DATA_DIR / f"{normalized}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(words, f, ensure_ascii=False, indent=2)

        summary_path = DATA_DIR / "unit_summaries" / f"{normalized}.md"
        if not summary_path.exists():
            summary_path.write_text(f"# {normalized}\n\n写下本子单元的学习目标、关键词、易错项。", encoding="utf-8")

        unit_entries.append({
            "unit": normalized,
            "count": len(words),
            "updated_at": datetime.utcnow().isoformat() + "Z",
        })

    index_path = DATA_DIR / "units.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(unit_entries, f, ensure_ascii=False, indent=2)

    # Compute relations
    print("Computing word relations...")
    model = SentenceTransformer('all-MiniLM-L6-v2')
    embeddings = model.encode([w['word'] for w in all_words])
    similarities = cosine_similarity(embeddings)

    relations = {}
    for i, word_entry in enumerate(all_words):
        word = word_entry['word']
        sim_scores = similarities[i]
        # top5 related (excluding self)
        related_indices = np.argsort(sim_scores)[::-1][1:6]
        related = [{'word': all_words[j]['word'], 'unit': all_words[j]['unit'], 'similarity': float(sim_scores[j])} for j in related_indices]
        # top3 opposite (lowest similarity)
        opposite_indices = np.argsort(sim_scores)[:3]
        opposite = [{'word': all_words[j]['word'], 'unit': all_words[j]['unit'], 'similarity': float(sim_scores[j])} for j in opposite_indices]
        relations[word] = {'related': related, 'opposite': opposite}

    relations_path = DATA_DIR / "relations.json"
    with open(relations_path, "w", encoding="utf-8") as f:
        json.dump(relations, f, ensure_ascii=False, indent=2)

    print(f"Initialized {len(unit_entries)} unit files and relations in {DATA_DIR}")


if __name__ == "__main__":
    init_data()
