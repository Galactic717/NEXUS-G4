# server/database.py
import logging
import time
import functools
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable, TypeVar

from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, event
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.pool import NullPool

from config import settings

logger = logging.getLogger("AI-Search-Database")

F = TypeVar("F", bound=Callable[..., Any])

db_file = Path(__file__).parent / settings.database_path
db_file = db_file.resolve()
db_file.parent.mkdir(parents=True, exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{db_file}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=NullPool,
    pool_pre_ping=True,
)

@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def retry(max_attempts: int = 3, delay: float = 0.1) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if "database is locked" in str(e) and attempt < max_attempts - 1:
                        time.sleep(delay * (attempt + 1))
                        continue
                    raise
            raise last_error
        return wrapper
    return decorator


class Research(Base):
    __tablename__ = "researches"

    id = Column(Integer, primary_key=True, index=True)
    query = Column(String, nullable=False)
    answer = Column(String, nullable=True)
    created_at = Column(String, nullable=False, default=lambda: datetime.now().isoformat())

    sources = relationship("Source", back_populates="research", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="research", order_by="Message.created_at", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    research_id = Column(Integer, ForeignKey("researches.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(String, nullable=False)
    created_at = Column(String, nullable=False, default=lambda: datetime.now().isoformat())

    research = relationship("Research", back_populates="messages")

class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    research_id = Column(Integer, ForeignKey("researches.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(String)
    title = Column(String, nullable=False)
    url = Column(String, nullable=False)
    snippet = Column(String)
    relevance_score = Column(Float)
    fetched_at = Column(String)

    research = relationship("Research", back_populates="sources")

class News(Base):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    url = Column(String, nullable=False, unique=True)
    source = Column(String, nullable=False)
    content = Column(String)
    date_added = Column(String, nullable=False, default=lambda: datetime.now().isoformat())


def init_db() -> None:
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _save_sources(db, research_id: int, sources_list: List[Dict[str, Any]]) -> None:
    for src in sources_list:
        new_source = Source(
            research_id=research_id,
            source_id=src.get("id") or src.get("source_id"),
            title=src.get("title") or "Джерело без назви",
            url=src.get("url") or "",
            snippet=src.get("content") or src.get("snippet") or "",
            relevance_score=src.get("relevance_score") or 0.0,
            fetched_at=src.get("fetched_at"),
        )
        db.add(new_source)

def _seed_messages(db, research_id: int, query: str, answer: str) -> None:
    user = Message(research_id=research_id, role="user", content=query, created_at=(datetime.now() - timedelta(seconds=1)).isoformat())
    assistant = Message(research_id=research_id, role="assistant", content=answer, created_at=datetime.now().isoformat())
    db.add(user)
    db.add(assistant)

@retry(max_attempts=3)
def save_research(query: str, answer: str, sources_list: List[Dict[str, Any]], research_id: Optional[int] = None) -> int:
    db = SessionLocal()
    try:
        if research_id:
            research = db.query(Research).filter(Research.id == research_id).first()
            if not research:
                research_id = None
            else:
                research.answer = answer

                if not research.messages:
                    _seed_messages(db, research.id, research.query, research.answer or "")
                    db.commit()

                user_msg = Message(research_id=research.id, role="user", content=query, created_at=(datetime.now() - timedelta(seconds=1)).isoformat())
                assistant_msg = Message(research_id=research.id, role="assistant", content=answer, created_at=datetime.now().isoformat())
                db.add(user_msg)
                db.add(assistant_msg)

                _save_sources(db, research.id, sources_list)
                db.commit()
                return research.id

        if not research_id:
            new_research = Research(query=query, answer=answer)
            db.add(new_research)
            db.commit()
            db.refresh(new_research)

            _seed_messages(db, new_research.id, query, answer)
            _save_sources(db, new_research.id, sources_list)
            db.commit()
            return new_research.id
    except Exception:
        db.rollback()
        logger.exception("Failed to save research")
        raise
    finally:
        db.close()

def get_history() -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        researches = db.query(Research).order_by(Research.created_at.desc()).all()
        return [{"id": r.id, "query": r.query, "created_at": r.created_at} for r in researches]
    finally:
        db.close()

def get_research_by_id(research_id: int) -> Optional[Dict[str, Any]]:
    db = SessionLocal()
    try:
        research = db.query(Research).filter(Research.id == research_id).first()
        if not research:
            return None

        if not research.messages:
            _seed_messages(db, research.id, research.query, research.answer or "")
            db.commit()
            db.refresh(research)

        sources = [
            {
                "id": src.source_id or f"S{src.id}",
                "title": src.title,
                "url": src.url,
                "content": src.snippet,
                "relevance_score": src.relevance_score,
                "fetched_at": src.fetched_at,
            }
            for src in research.sources
        ]

        return {
            "id": research.id,
            "query": research.query,
            "answer": research.answer,
            "created_at": research.created_at,
            "sources": sources,
            "messages": [{"role": m.role, "content": m.content} for m in research.messages],
        }
    except Exception:
        db.rollback()
        logger.exception("Failed to get research by id")
        raise
    finally:
        db.close()

def get_research_by_query(query: str) -> Optional[Dict[str, Any]]:
    db = SessionLocal()
    try:
        research = db.query(Research).filter(Research.query.ilike(query)).order_by(Research.created_at.desc()).first()
        if research:
            return get_research_by_id(research.id)
        return None
    finally:
        db.close()

def delete_research(research_id: int) -> bool:
    db = SessionLocal()
    try:
        research = db.query(Research).filter(Research.id == research_id).first()
        if research:
            db.delete(research)
            db.commit()
            return True
        return False
    except Exception:
        db.rollback()
        logger.exception("Failed to delete research")
        raise
    finally:
        db.close()


def add_news(title: str, url: str, source: str, content: str, custom_date: Optional[str] = None) -> bool:
    # Базова валідація
    if not title or not url or not source:
        return False

    if not url.startswith("http://") and not url.startswith("https://"):
        return False

    db = SessionLocal()
    try:
        existing = db.query(News).filter(News.url == url).first()
        if existing:
            return False

        date_added = custom_date or datetime.now().isoformat()
        db.add(News(title=title, url=url, source=source, content=content, date_added=date_added))
        db.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding news: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def get_latest_news(limit: int = 20) -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        news_items = db.query(News).order_by(News.date_added.desc()).limit(limit).all()
        return [
            {
                "id": n.id,
                "title": n.title,
                "url": n.url,
                "source": n.source,
                "content": n.content,
                "date_added": n.date_added,
            }
            for n in news_items
        ]
    finally:
        db.close()

def delete_old_news(days: int) -> int:
    db = SessionLocal()
    try:
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        count = db.query(News).filter(News.date_added < cutoff_date).delete()
        db.commit()
        return count
    except Exception as e:
        logger.error(f"Error deleting old news: {e}")
        db.rollback()
        return 0
    finally:
        db.close()


init_db()
