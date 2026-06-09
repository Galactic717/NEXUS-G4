import argparse
import json
import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any, List

from . import config
from .client import (
    check_server,
    research_stream,
    get_history,
    get_research_detail,
    delete_research,
    get_news,
    repopulate_news,
    export_pdf,
    export_html,
)
from .local_cache import (
    init_cache,
    save_to_cache,
    search_cache,
    get_all_cached,
    get_cached_by_id,
    update_tags,
    delete_from_cache,
    clear_cache,
    get_cache_stats,
)
from .local_processor import (
    preprocess_query,
    extract_keywords,
    deduplicate_sources,
    rerank_sources,
    filter_by_keywords,
    truncate_answer,
)
from .local_exporter import (
    export_markdown,
    export_json,
    export_txt_concise,
)


def cmd_status(args):
    ok = check_server()
    if ok:
        print(f"Server: {config.get('server_url')} - ONLINE")
    else:
        print(f"Server: {config.get('server_url')} - OFFLINE")

    stats = get_cache_stats()
    print(f"Local cache: {stats['total_entries']} entries, {stats['total_chars']} chars")


def cmd_search(args):
    if not check_server():
        print("Error: Server is offline")
        sys.exit(1)

    query_raw = " ".join(args.query)
    loops = args.loops if args.loops is not None else config.get("default_loops", 0)

    processed = preprocess_query(query_raw)
    if processed != query_raw:
        print(f"[Preprocessed] {query_raw} -> {processed}")

    keywords = extract_keywords(processed)
    print(f"[Keywords] {', '.join(keywords)}")
    print(f"[Researching] loops={loops}, search_only={args.search_only}")
    print()

    full_answer = ""
    all_sources = []
    research_id = None
    used_tokens = 0

    for event in research_stream(
        query=processed,
        loops=loops,
        search_only=args.search_only,
        research_id=args.session,
    ):
        etype = event.get("type")

        if etype == "token":
            content = event.get("content", "")
            full_answer += content
            print(content, end="", flush=True)

        elif etype == "sources":
            all_sources = event.get("sources", [])

        elif etype == "context":
            used_tokens = event.get("used_tokens", 0)
            remaining = event.get("remaining_percent", 100)
            if remaining < 20:
                print(f"\n[Context memory: {remaining}% remaining, {used_tokens} tokens used]")

        elif etype == "warning":
            print(f"\n[WARNING] {event.get('message', '')}")

        elif etype == "error":
            print(f"\n[ERROR] {event.get('message', '')}")
            return

        elif etype == "done":
            research_id = event.get("id")
            print()

    if not full_answer and not all_sources:
        print("No results received.")
        return

    if all_sources:
        all_sources = deduplicate_sources(all_sources)
        all_sources = rerank_sources(all_sources, keywords)
        if args.filter_keywords:
            all_sources = filter_by_keywords(all_sources, args.filter_keywords)

    cache_id = save_to_cache(
        query=query_raw,
        answer=full_answer,
        sources=all_sources,
        server_id=research_id,
        tags=",".join(keywords[:5]),
    )
    print(f"\n[Saved to local cache: #{cache_id}]")

    if args.export:
        _do_export(query_raw, full_answer, all_sources, args.export)

    if args.show_sources:
        _print_sources(all_sources)

    if args.tokens:
        print(f"\n[Tokens used: {used_tokens}]")


def cmd_chat(args):
    if not check_server():
        print("Error: Server is offline")
        sys.exit(1)

    sid = args.session
    if sid:
        cached = get_cached_by_id(sid)
        if cached:
            print(f"Restoring session: {cached['query']}")
            print()

    query_raw = " ".join(args.query)
    processed = preprocess_query(query_raw)
    if processed != query_raw:
        print(f"[Preprocessed] {query_raw} -> {processed}")

    keywords = extract_keywords(processed)
    print(f"[Keywords] {', '.join(keywords)}")

    full_answer = ""
    all_sources = []
    research_id = None

    for event in research_stream(
        query=processed,
        loops=0,
        search_only=False,
        research_id=sid,
    ):
        etype = event.get("type")

        if etype == "token":
            content = event.get("content", "")
            full_answer += content
            print(content, end="", flush=True)

        elif etype == "sources":
            all_sources = event.get("sources", [])

        elif etype == "error":
            print(f"\n[ERROR] {event.get('message', '')}")
            return

        elif etype == "done":
            research_id = event.get("id")
            print()

    if all_sources:
        all_sources = deduplicate_sources(all_sources)
        all_sources = rerank_sources(all_sources, keywords)

    save_to_cache(
        query=query_raw,
        answer=full_answer,
        sources=all_sources,
        server_id=research_id,
        tags=",".join(keywords[:5]),
    )

    if args.show_sources:
        _print_sources(all_sources)


def cmd_history(args):
    if not check_server():
        print("Error: Server is offline")
        sys.exit(1)

    if args.local:
        entries = get_all_cached(limit=args.limit)
        if not entries:
            print("Local cache is empty.")
            return
        for e in entries:
            print(f"  #{e['id']:4d} | {e['query'][:60]:60s} | tags: {e['tags']}")
        return

    items = get_history()
    if not items:
        print("Server history is empty.")
        return
    for item in items:
        print(f"  #{item['id']:4d} | {item['query'][:60]:60s} | {item.get('created_at', '')[:19]}")


def cmd_get(args):
    if not check_server():
        print("Error: Server is offline")
        sys.exit(1)

    if args.local:
        record = get_cached_by_id(args.id)
        if not record:
            print(f"No local record #{args.id}")
            return
        print(f"Query: {record['query']}")
        print(f"Cached: {record.get('created_at', '')}")
        print(f"Tags: {record.get('tags', '')}")
        print(f"Sources: {len(record.get('sources', []))}")
        print()
        print(record.get("answer", ""))
        if args.sources:
            print()
            _print_sources(record.get("sources", []))
        return

    detail = get_research_detail(args.id)
    if not detail:
        print(f"Server has no record #{args.id}")
        return
    print(f"Query: {detail['query']}")
    print(f"Created: {detail.get('created_at', '')}")
    print(f"Context: {detail.get('remaining_context_percent', 'N/A')}%")
    print()
    print(detail.get("answer", ""))
    if args.sources:
        print()
        _print_sources(detail.get("sources", []))


def cmd_delete(args):
    if args.all:
        clear_cache()
        print("Local cache cleared.")
        return

    if args.id:
        ok = delete_from_cache(args.id)
        if ok:
            print(f"Deleted #{args.id} from local cache")
        else:
            print(f"No local record #{args.id}")

    if args.server_id:
        if check_server():
            ok = delete_research(args.server_id)
            if ok:
                print(f"Deleted #{args.server_id} from server")
            else:
                print(f"No server record #{args.server_id}")
        else:
            print("Server is offline, cannot delete on server.")


def cmd_cache(args):
    if args.stats:
        stats = get_cache_stats()
        print("Local cache statistics:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        return

    if args.search:
        results = search_cache(" ".join(args.search), limit=args.limit)
        if not results:
            print("No local matches.")
            return
        for r in results:
            print(f"  #{r['id']:4d} | {r['query'][:60]:60s} | rank: {r.get('rank', '?')}")
        return

    if args.tag:
        cid, tag_val = args.tag
        update_tags(cid, tag_val)
        print(f"Updated tags for #{cid}: {tag_val}")
        return

    entries = get_all_cached(limit=args.limit, offset=args.offset)
    if not entries:
        print("Local cache is empty.")
        return
    for e in entries:
        kw = extract_keywords(e["query"], 3)
        print(f"  #{e['id']:4d} | {e['query'][:50]:50s} | keywords: {', '.join(kw)}")


def cmd_news(args):
    if not check_server():
        print("Error: Server is offline")
        sys.exit(1)

    if args.repopulate:
        ok = repopulate_news()
        print("News repopulated." if ok else "Failed to repopulate news.")
        return

    news = get_news(limit=args.limit)
    if not news:
        print("No news available.")
        return
    for n in news:
        print(f"  [{n.get('date_added', '')[:10]}] {n.get('title', '')}")
        print(f"       {n.get('url', '')}")
        print()


def cmd_export(args):
    if not check_server():
        print("Error: Server is offline")
        sys.exit(1)

    research = get_research_detail(args.id)
    if not research:
        print(f"No server record #{args.id}")
        return

    query = research["query"]
    answer = research["answer"]
    sources = research.get("sources", [])

    _do_export(query, answer, sources, args.format)


def _do_export(query: str, answer: str, sources: List[Dict[str, Any]], fmt: str):
    if fmt == "md":
        path = export_markdown(query, answer, sources)
        print(f"Exported: {path}")
    elif fmt == "txt":
        path = export_txt_concise(query, answer, sources)
        print(f"Exported: {path}")
    elif fmt == "json":
        path = export_json({
            "query": query,
            "answer": answer,
            "sources": sources,
        })
        print(f"Exported: {path}")
    elif fmt == "pdf":
        print("Server-side PDF export...")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = str(config.EXPORT_DIR / f"report_{args.id}_{ts}.pdf")
        ok = export_pdf(args.id, out)
        print(f"Exported: {out}" if ok else "PDF export failed.")
    elif fmt == "html":
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = str(config.EXPORT_DIR / f"report_{args.id}_{ts}.html")
        ok = export_html(args.id, out)
        print(f"Exported: {out}" if ok else "HTML export failed.")


def cmd_config(args):
    if args.show:
        cfg = config.load_config()
        for k, v in cfg.items():
            print(f"  {k}: {v}")
        return

    if args.key and args.value:
        config.set_key(args.key, args.value)
        print(f"Set {args.key} = {args.value}")


def _print_sources(sources: List[Dict[str, Any]]):
    if not sources:
        print("  No sources.")
        return
    print(f"\nSources ({len(sources)}):")
    for i, s in enumerate(sources, 1):
        title = s.get("title", "Untitled")
        url = s.get("url", "")
        relevance = s.get("relevance_score", "N/A")
        print(f"  [{i}] {title}")
        print(f"       {url}")
        print(f"       relevance: {relevance}")
        snippet = s.get("snippet", "")
        if snippet:
            print(f"       {snippet[:100]}")
        print()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ai-cli",
        description="Specialized CLI client for AI OSINT Deep Research Tool",
    )
    p.add_argument("--version", action="version", version="ai-cli 1.0.0")

    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("status", help="Check server and cache status")

    search = sub.add_parser("search", help="Run a research query")
    search.add_argument("query", nargs="+", help="Search query")
    search.add_argument("--loops", type=int, default=None, help="Deep research loops (0-3)")
    search.add_argument("--search-only", action="store_true", help="Search only mode")
    search.add_argument("--session", type=int, help="Continue existing session")
    search.add_argument("--export", choices=["md", "txt", "json"], help="Export format")
    search.add_argument("--show-sources", action="store_true", help="Show sources")
    search.add_argument("--tokens", action="store_true", help="Show token count")
    search.add_argument("--filter-keywords", nargs="*", help="Filter sources by keywords")

    chat = sub.add_parser("chat", help="Chat with research (0 loops, streaming)")
    chat.add_argument("query", nargs="+", help="Chat message")
    chat.add_argument("--session", type=int, help="Continue existing session ID")
    chat.add_argument("--show-sources", action="store_true", help="Show sources")

    history = sub.add_parser("history", help="Show research history")
    history.add_argument("--local", action="store_true", help="Show local cache instead")
    history.add_argument("--limit", type=int, default=20, help="Max entries")

    get = sub.add_parser("get", help="Get research details")
    get.add_argument("id", type=int, help="Research ID")
    get.add_argument("--local", action="store_true", help="Get from local cache")
    get.add_argument("--sources", action="store_true", help="Show sources")

    delete = sub.add_parser("delete", help="Delete research records")
    delete.add_argument("--id", type=int, help="Local cache ID")
    delete.add_argument("--server-id", type=int, help="Server ID")
    delete.add_argument("--all", action="store_true", help="Clear entire local cache")

    cache = sub.add_parser("cache", help="Manage local cache")
    cache.add_argument("--stats", action="store_true", help="Show cache statistics")
    cache.add_argument("--search", nargs="+", help="Full-text search local cache")
    cache.add_argument("--tag", nargs=2, metavar=("ID", "TAGS"), help="Tag a cached entry")
    cache.add_argument("--limit", type=int, default=20, help="Max entries")
    cache.add_argument("--offset", type=int, default=0, help="Offset")

    news = sub.add_parser("news", help="Browse AI news")
    news.add_argument("--limit", type=int, default=10, help="Number of news items")
    news.add_argument("--repopulate", action="store_true", help="Repopulate news database")

    export = sub.add_parser("export", help="Export research report")
    export.add_argument("id", type=int, help="Server research ID")
    export.add_argument("format", choices=["md", "txt", "json", "pdf", "html"], help="Export format")

    cfg = sub.add_parser("config", help="View/set configuration")
    cfg.add_argument("--show", action="store_true", help="Show all config")
    cfg.add_argument("--key", help="Config key")
    cfg.add_argument("--value", help="Config value")

    return p


def main():
    init_cache()
    parser = build_parser()
    args = parser.parse_args()

    command_map = {
        "status": cmd_status,
        "search": cmd_search,
        "chat": cmd_chat,
        "history": cmd_history,
        "get": cmd_get,
        "delete": cmd_delete,
        "cache": cmd_cache,
        "news": cmd_news,
        "export": cmd_export,
        "config": cmd_config,
    }

    cmd = command_map.get(args.command)
    if cmd:
        cmd(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
