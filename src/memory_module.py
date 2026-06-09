import logging
import re
from datetime import datetime
from typing import List, Optional
from sqlalchemy import Column, String, Text, Float, Integer, DateTime, func
from database import Base, SessionLocal, engine

logger = logging.getLogger("AI-Search-Memory")

class MemoryEntry(Base):
    __tablename__ = "ai_memory"
    query = Column(String, primary_key=True)
    summary = Column(Text, nullable=False)

class KnowledgeFact(Base):
    __tablename__ = "knowledge_facts"
    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String, nullable=False, index=True)
    fact = Column(Text, nullable=False)
    source_url = Column(String, default="")
    confidence = Column(Float, default=1.0)
    access_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed = Column(DateTime, default=datetime.utcnow)

def init_memory_db():
    Base.metadata.create_all(bind=engine)
    logger.info("Memory database tables initialized.")

def _extract_key_phrases(text: str) -> List[str]:
    words = re.findall(r"[\w\u0400-\u04ff]{3,}", text.lower())
    seen = set()
    phrases = []
    for w in words:
        if w not in seen:
            seen.add(w)
            phrases.append(w)
    return phrases

def _compute_relevance(query_phrases: List[str], fact_text: str) -> float:
    fact_lower = fact_text.lower()
    hits = sum(1 for p in query_phrases if p in fact_lower)
    if not hits:
        return 0.0
    base = hits / max(len(query_phrases), 1)
    exact_phrase_bonus = 0.2 if any(p in fact_lower for p in [" ".join(query_phrases[i:i+2]) for i in range(len(query_phrases)-1)]) else 0.0
    return min(base + exact_phrase_bonus, 1.0)

def save_to_memory(query: str, summary: str):
    db = SessionLocal()
    try:
        existing = db.query(MemoryEntry).filter(MemoryEntry.query == query).first()
        if existing:
            existing.summary = summary
        else:
            new_entry = MemoryEntry(query=query, summary=summary)
            db.add(new_entry)
        db.commit()
        logger.info(f"Knowledge about '{query}' added to memory.")
        _extract_and_store_facts(query, summary)
    except Exception as e:
        logger.error(f"Error saving to memory: {e}")
        db.rollback()
    finally:
        db.close()

def _extract_and_store_facts(topic: str, text: str):
    db = SessionLocal()
    try:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        urls = re.findall(r'https?://[^\s)]+', text)
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 30 or len(sentence) > 2000:
                continue
            if any(sentence.startswith(p) for p in ["###", "**", "*", "- [", "[S"]):
                continue
            has_number = bool(re.search(r'\d+', sentence))
            has_keyword = any(kw in sentence.lower() for kw in [
                "досяг", "становить", "перевищ", "показ", "результат",
                "виявив", "встановлен", "згідно", "за даними", "на основі",
                "продемонстр", "забезпеч", "дозволя", "використов",
                "архітектур", "метод", "алгоритм", "модель", "систем",
            ])
            if not (has_number or has_keyword):
                continue
            existing = db.query(KnowledgeFact).filter(
                KnowledgeFact.fact == sentence,
                KnowledgeFact.topic == topic[:200]
            ).first()
            if existing:
                existing.access_count = KnowledgeFact.access_count + 1
                existing.last_accessed = datetime.utcnow()
            else:
                fact = KnowledgeFact(
                    topic=topic[:200],
                    fact=sentence,
                    source_url=urls[0] if urls else "",
                    confidence=0.7 if has_number else 0.5,
                )
                db.add(fact)
        db.commit()
        logger.info(f"Extracted facts from research on '{topic[:50]}'")
    except Exception as e:
        logger.error(f"Error extracting facts: {e}")
        db.rollback()
    finally:
        db.close()

def search_memory(query: str) -> str:
    db = SessionLocal()
    try:
        keywords = query.lower().split()
        if not keywords:
            return ""
        memory_results = db.query(MemoryEntry).filter(
            MemoryEntry.summary.ilike(f"%{keywords[0]}%")
        ).limit(2).all()

        result_parts = []
        if memory_results:
            for res in memory_results:
                result_parts.append(f"ФАКТ З ВЛАСНОЇ ПАМ'ЯТІ:\n{res.summary}")
        fact_results = search_knowledge_facts(query, top_k=5)
        if fact_results:
            facts_text = "\n".join(f"- {f.fact}" for f in fact_results)
            result_parts.append(f"ВИТЯГНУТІ ФАКТИ:\n{facts_text}")
        if result_parts:
            return f"\n[ЗГОРНУТІ ЗНАННЯ З МИНУЛИХ ДОСЛІДЖЕНЬ]:\n{chr(10).join(result_parts)}\n"
        return ""
    except Exception as e:
        logger.error(f"Error searching memory: {e}")
        return ""
    finally:
        db.close()

def search_knowledge_facts(query: str, top_k: int = 5):
    db = SessionLocal()
    try:
        query_phrases = _extract_key_phrases(query)
        if not query_phrases:
            return []
        all_facts = db.query(KnowledgeFact).all()
        scored = []
        for fact in all_facts:
            relevance = _compute_relevance(query_phrases, fact.fact + " " + fact.topic)
            days_since_access = (datetime.utcnow() - fact.last_accessed).days if fact.last_accessed else 365
            recency_boost = max(0.0, 0.1 * (1 - days_since_access / 365))
            access_boost = min(0.1, fact.access_count * 0.02) if fact.access_count else 0.0
            final_score = relevance + recency_boost + access_boost
            if final_score > 0.15:
                scored.append((final_score, fact))
        scored.sort(key=lambda x: x[0], reverse=True)
        result = [f for _, f in scored[:top_k]]
        for fact in result:
            fact.access_count = (fact.access_count or 0) + 1
            fact.last_accessed = datetime.utcnow()
        db.commit()
        return result
    except Exception as e:
        logger.error(f"Error searching knowledge facts: {e}")
        return []
    finally:
        db.close()

def consolidate_memory(query: str):
    db = SessionLocal()
    try:
        related = db.query(KnowledgeFact).filter(
            KnowledgeFact.topic.ilike(f"%{query[:100]}%")
        ).order_by(KnowledgeFact.access_count.desc()).limit(10).all()
        if len(related) >= 3:
            combined_topic = f"Консолідовано: {query[:100]}"
            combined_fact = " | ".join([f.fact[:300] for f in related[:5]])
            existing = db.query(MemoryEntry).filter(MemoryEntry.query == combined_topic).first()
            if existing:
                existing.summary = combined_fact
            else:
                db.add(MemoryEntry(query=combined_topic, summary=combined_fact))
            db.commit()
            logger.info(f"Consolidated memory for '{query[:50]}' — linked {len(related)} facts")
    except Exception as e:
        logger.error(f"Error consolidating memory: {e}")
    finally:
        db.close()

init_memory_db()
