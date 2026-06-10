import os
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from ollama_deep_researcher.utils import pubmed_search

def test_pubmed():
    print("Testing PubMed search...")
    query = "CRISPR gene editing breakthroughs 2026"
    results = pubmed_search(query, max_results=3)
    
    if results.get("results"):
        print(f"Success! Found {len(results['results'])} results.")
        for res in results["results"]:
            print(f"- {res['title']} ({res['url']})")
    else:
        print("No results found or error occurred.")

if __name__ == "__main__":
    test_pubmed()
