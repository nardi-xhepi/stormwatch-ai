#!/usr/bin/env python3
"""
Benchmark: Cross-lingual news article retrieval
Compares all-MiniLM-L6-v2 vs paraphrase-multilingual-MiniLM-L12-v2

Tests English queries against French news article excerpts from Le Monde.
"""

import time
import json
from sentence_transformers import SentenceTransformer
import numpy as np

# Real test pairs: English queries matched with actual Le Monde article excerpts
NEWS_TEST_PAIRS = [
    {
        "english_query": "What are the cold weather protection measures?",
        "french_article": "Plan Grand Froid : plusieurs préfectures ont actionné des mesures d'urgence pour protéger les plus vulnérables face au froid.",
        "topic": "Cold weather measures"
    },
    {
        "english_query": "What emergency actions have been taken by the government?",
        "french_article": "Face à la vague hivernale, la Mairie de Paris réclame le déclenchement du plan Grand Froid, l'État répond être largement mobilisé.",
        "topic": "Emergency actions"
    },
    {
        "english_query": "Is there a flood warning in the region?",
        "french_article": "Pluie-inondation : la vigilance orange maintenue dans les Pyrénées-Orientales. Les cumuls attendus sont compris entre 30 et 50 millimètres.",
        "topic": "Flood warning"
    },
    {
        "english_query": "Are there any storm warnings?",
        "french_article": "Pluie-inondations : la vigilance orange levée en Haute-Corse ; les Pyrénées-Orientales et l'Aude maintenues en alerte pour les crues.",
        "topic": "Storm warnings"
    },
    {
        "english_query": "Will it snow tomorrow?",
        "french_article": "Neige en France : deux départements en vigilance orange, des chutes de 5 cm à 10 cm localement.",
        "topic": "Snow forecast"
    },
    {
        "english_query": "How strong is the wind today?",
        "french_article": "Vents violents attendus sur la côte atlantique avec des rafales jusqu'à 100 km/h selon Météo-France.",
        "topic": "Wind conditions"
    },
]


def cosine_similarity(v1, v2):
    """Calculate cosine similarity between two vectors."""
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))


def benchmark_model(model_name: str) -> dict:
    """Run news retrieval benchmark for a given model."""
    print(f"\n{'='*60}")
    print(f"Model: {model_name}")
    print("="*60)
    
    start_load = time.time()
    model = SentenceTransformer(model_name)
    load_time = time.time() - start_load
    print(f"Loaded in {load_time:.2f}s (dimension: {model.get_sentence_embedding_dimension()})")
    
    results = {
        "model_name": model_name,
        "dimension": model.get_sentence_embedding_dimension(),
        "load_time_s": round(load_time, 2),
        "scores": [],
    }
    
    print("\n--- Cross-lingual News Retrieval (EN → FR) ---")
    for pair in NEWS_TEST_PAIRS:
        emb_query = model.encode(pair["english_query"])
        emb_article = model.encode(pair["french_article"])
        sim = cosine_similarity(emb_query, emb_article)
        results["scores"].append({
            "topic": pair["topic"],
            "similarity": round(float(sim), 4)
        })
        print(f"  {pair['topic']:<25} {sim:.4f}")
    
    results["average"] = round(np.mean([s["similarity"] for s in results["scores"]]), 4)
    print(f"\n  {'AVERAGE':<25} {results['average']:.4f}")
    
    return results


def main():
    print("="*60)
    print("CROSS-LINGUAL NEWS RETRIEVAL BENCHMARK")
    print("English queries → French Le Monde articles")
    print("="*60)
    
    models = [
        "all-MiniLM-L6-v2",
        "paraphrase-multilingual-MiniLM-L12-v2"
    ]
    
    all_results = {}
    for model_name in models:
        all_results[model_name] = benchmark_model(model_name)
    
    # Print comparison
    mini = all_results["all-MiniLM-L6-v2"]
    multi = all_results["paraphrase-multilingual-MiniLM-L12-v2"]
    
    print("\n" + "="*60)
    print("COMPARISON SUMMARY")
    print("="*60)
    print(f"\n{'Topic':<25} {'MiniLM':<10} {'Multi':<10} {'Δ':<10}")
    print("-"*55)
    
    for i, score_mini in enumerate(mini["scores"]):
        score_multi = multi["scores"][i]
        improvement = (score_multi["similarity"] / score_mini["similarity"] - 1) * 100
        print(f"{score_mini['topic']:<25} {score_mini['similarity']:<10.4f} {score_multi['similarity']:<10.4f} +{improvement:.0f}%")
    
    avg_improvement = (multi["average"] / mini["average"] - 1) * 100
    print("-"*55)
    print(f"{'AVERAGE':<25} {mini['average']:<10.4f} {multi['average']:<10.4f} +{avg_improvement:.0f}%")
    
    # Save results
    with open("benchmark_results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    print("\nResults saved to benchmark_results.json")
    
    return all_results


if __name__ == "__main__":
    main()
