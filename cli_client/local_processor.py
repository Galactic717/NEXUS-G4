import re
from datetime import date
from typing import List, Dict, Any, Set

ACRONYM_MAP = {
    r"\bAI\b": "AI artificial intelligence machine learning neural network",
    r"\bLLM\b": "LLM large language model",
    r"\bML\b": "ML machine learning",
    r"\bNLP\b": "NLP natural language processing",
    r"\bRAG\b": "RAG retrieval augmented generation",
    r"\bRLHF\b": "RLHF reinforcement learning from human feedback",
    r"\bGNN\b": "GNN graph neural network",
    r"\bCNN\b": "CNN convolutional neural network",
    r"\bRNN\b": "RNN recurrent neural network",
    r"\bGAN\b": "GAN generative adversarial network",
    r"\bVAE\b": "VAE variational autoencoder",
    r"\bMCP\b": "MCP model context protocol",
    r"\bAPI\b": "API application programming interface",
    r"\bSDK\b": "SDK software development kit",
    r"\bGPU\b": "GPU graphics processing unit",
    r"\bTPU\b": "TPU tensor processing unit",
    r"\bAGI\b": "AGI artificial general intelligence",
    r"\bASI\b": "ASI artificial super intelligence",
}

TEMPORAL_WORDS = [
    "today", "yesterday", "latest", "recent", "this week",
    "this month", "this year", "нові", "останні", "сьогодні",
    "вчора", "новин", "актуальн",
]

LEADING_NOISE = re.compile(
    r"^(коротко|стисло|брифінг|briefly|short|summarize|tell me about|"
    r"what is|what are|who is|explain|describe)\s+",
    re.IGNORECASE,
)

QUESTION_WORDS = re.compile(r"^(що|хто|як|де|коли|чому|який|яка|які|what|who|how|where|when|why)\s+", re.IGNORECASE)


def preprocess_query(query: str) -> str:
    processed = query.strip()
    processed = LEADING_NOISE.sub("", processed).strip()
    processed = QUESTION_WORDS.sub("", processed).strip()
    for pattern, replacement in ACRONYM_MAP.items():
        processed = re.sub(pattern, replacement, processed)
    has_temporal = any(w in query.lower() for w in TEMPORAL_WORDS)
    if has_temporal:
        today = date.today().isoformat()
        if "today" not in processed.lower():
            processed += f" (date: {today})"
    return processed


def extract_keywords(text: str, max_words: int = 10) -> List[str]:
    words = re.findall(r"[А-Яа-яA-Za-z]{3,}", text.lower())
    stop_words = {
        "this", "that", "and", "the", "for", "are", "but", "not",
        "you", "all", "can", "had", "her", "was", "one", "our",
        "out", "has", "have", "been", "its", "than", "what",
        "from", "they", "with", "та", "і", "в", "на", "не",
        "що", "як", "до", "за", "але", "або", "чи", "з",
        "про", "по", "це", "його", "її", "який", "такий",
    }
    return [w for w in words if w not in stop_words][:max_words]


def deduplicate_sources(
    sources: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    seen_urls: Set[str] = set()
    seen_titles: Set[str] = set()
    deduped = []
    for s in sources:
        url = (s.get("url") or "").strip().lower()
        title = (s.get("title") or "").strip().lower()
        if url and url in seen_urls:
            continue
        if title and title in seen_titles:
            continue
        if url:
            seen_urls.add(url)
        if title:
            seen_titles.add(title)
        deduped.append(s)
    return deduped


def rerank_sources(
    sources: List[Dict[str, Any]],
    query_keywords: List[str],
) -> List[Dict[str, Any]]:
    scored = []
    for s in sources:
        score = s.get("relevance_score", 5.0)
        title = (s.get("title") or "").lower()
        snippet = (s.get("snippet") or "").lower()
        combined = f"{title} {snippet}"
        for kw in query_keywords:
            if kw in combined:
                score += 2.0
        if s.get("url", "").startswith("http"):
            score += 1.0
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored]


def filter_by_keywords(
    sources: List[Dict[str, Any]], keywords: List[str]
) -> List[Dict[str, Any]]:
    if not keywords:
        return sources
    result = []
    for s in sources:
        text = f"{s.get('title', '')} {s.get('snippet', '')} {s.get('content', '')}".lower()
        if any(kw.lower() in text for kw in keywords):
            result.append(s)
    return result


def truncate_answer(answer: str, max_chars: int = 2000) -> str:
    if len(answer) <= max_chars:
        return answer
    return answer[:max_chars] + "\n\n[...truncated]"
