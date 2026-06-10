import json
import re

from pydantic import BaseModel, Field
from typing_extensions import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.graph import START, END, StateGraph
from llm_factory import LLMFactory

from ollama_deep_researcher.configuration import Configuration, SearchAPI
from ollama_deep_researcher.utils import (
    deduplicate_and_format_sources,
    annotate_source_relevance,
    assign_source_ids,
    tavily_search,
    format_sources,
    perplexity_search,
    duckduckgo_search,
    searxng_search,
    parallel_search,
    strip_thinking_tokens,
    get_config_value,
    get_current_date,
    get_current_year,
)
from ollama_deep_researcher.state import (
    SummaryState,
    SummaryStateInput,
    SummaryStateOutput,
)
from ollama_deep_researcher.prompts import (
    query_writer_instructions,
    summarizer_instructions,
    reflection_instructions,
    json_mode_query_instructions,
    tool_calling_query_instructions,
    json_mode_reflection_instructions,
    tool_calling_reflection_instructions,
)
from ollama_deep_researcher.lmstudio import ChatLMStudio
from config import settings

# Константи
MAX_TOKENS_PER_SOURCE = 1000000
CHARS_PER_TOKEN = 4
SEARCH_RESULTS_PER_LOOP = 25  # Збільшено з 15 до 25 для глибшого аналізу
MAX_RESEARCH_LOOPS = 10

# Розширення запиту синонімами
SYNONYM_MAP = {
    r'\bAI\b': 'AI artificial intelligence machine learning deep learning',
    r'\bLLM\b': 'LLM large language model transformer',
    r'\bML\b': 'ML machine learning',
    r'\bNLP\b': 'NLP natural language processing',
    r'\bRAG\b': 'RAG retrieval augmented generation',
    r'\bGPU\b': 'GPU graphics processing unit',
    r'\bCNN\b': 'CNN convolutional neural network',
    r'\bRNN\b': 'RNN recurrent neural network',
    r'\bGAN\b': 'GAN generative adversarial network',
    r'\bSOTA\b': 'SOTA state of the art best',
}


def _expand_query_synonyms(query: str) -> str:
    expanded = query
    for pattern, replacement in SYNONYM_MAP.items():
        if re.search(pattern, query, re.IGNORECASE):
            words = replacement.split()
            for w in words:
                if w.lower() not in expanded.lower():
                    expanded += f" {w}"
    return expanded


def _has_new_information(old_sources: list, new_sources: list) -> bool:
    """Перевіряє, чи з'явилися нові джерела в поточному циклі."""
    old_urls = set()
    for src_list in old_sources:
        if isinstance(src_list, str):
            for line in src_list.split("\n"):
                if ": " in line:
                    url = line.split(": ")[-1].strip()
                    old_urls.add(url)
        elif isinstance(src_list, dict):
            old_urls.add(src_list.get("url", ""))
    new_urls = set()
    for src in new_sources:
        new_urls.add(src.get("url", ""))
    new_unique = new_urls - old_urls
    return len(new_unique) >= 2


def generate_search_query_with_structured_output(
    configurable: Configuration,
    messages: list,
    tool_class,
    fallback_query: str,
    tool_query_field: str,
    json_query_field: str,
):
    if configurable.use_tool_calling:
        llm = get_llm(configurable).bind_tools([tool_class])
        result = llm.invoke(messages)
        if not result.tool_calls:
            return {"search_query": fallback_query}
        try:
            tool_data = result.tool_calls[0]["args"]
            search_query = tool_data.get(tool_query_field)
            return {"search_query": search_query}
        except (IndexError, KeyError):
            return {"search_query": fallback_query}
    else:
        llm = get_llm(configurable)
        result = llm.invoke(messages)
        content = result.content
        parsed_json = _parse_json_model_output(
            content,
            strip_thinking=configurable.strip_thinking_tokens,
        )
        if not parsed_json:
            return {"search_query": fallback_query}
        search_query = parsed_json.get(json_query_field)
        if not search_query:
            return {"search_query": fallback_query}
        return {"search_query": search_query}


def _parse_json_model_output(
    content: str,
    *,
    strip_thinking: bool,
) -> dict:
    candidates = [content]
    if strip_thinking:
        cleaned = strip_thinking_tokens(content)
        if cleaned != content:
            candidates.append(cleaned)
    for candidate in candidates:
        candidate = candidate.strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            extracted = _extract_json_object(candidate)
            if not extracted:
                continue
            try:
                return json.loads(extracted)
            except json.JSONDecodeError:
                continue
    return {}


def _extract_json_object(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def get_llm(configurable: Configuration):
    if configurable.llm_provider == "lmstudio":
        if configurable.use_tool_calling:
            return ChatLMStudio(
                base_url=configurable.lmstudio_base_url,
                model=configurable.local_llm,
                temperature=0,
            )
        else:
            return ChatLMStudio(
                base_url=configurable.lmstudio_base_url,
                model=configurable.local_llm,
                temperature=0,
                format="json",
            )
    else:
        fmt = None if configurable.use_tool_calling else "json"
        return LLMFactory.get_llm(
            model_name=configurable.local_llm,
            temperature=0,
            num_gpu=-1,
            format=fmt,
            base_url=configurable.ollama_base_url,
        )


# Nodes
def generate_query(state: SummaryState, config: RunnableConfig):
    """
    LangGraph node: Generates an optimized search query based on the current research state.
    
    This node uses the LLM to analyze the research topic and identify the most 
    effective search terms, potentially using advanced search operators.
    """
    current_date = get_current_date()
    current_year = get_current_year()
    formatted_prompt = query_writer_instructions.format(
        current_date=current_date,
        current_year=current_year,
        research_topic=state.research_topic,
    )
    configurable = Configuration.from_runnable_config(config)

    @tool
    class Query(BaseModel):
        query: str = Field(description="The actual search query string")
        rationale: str = Field(
            description="Brief explanation of why this query is relevant"
        )

    messages = [
        SystemMessage(
            content=formatted_prompt + (
                tool_calling_query_instructions if configurable.use_tool_calling 
                else json_mode_query_instructions
            )
        ),
        HumanMessage(content="Generate a query for web search:"),
    ]

    result = generate_search_query_with_structured_output(
        configurable=configurable,
        messages=messages,
        tool_class=Query,
        fallback_query=f"Tell me more about {state.research_topic}",
        tool_query_field="query",
        json_query_field="query",
    )

    # Автоматичне розширення запиту синонімами
    if result.get("search_query"):
        result["search_query"] = _expand_query_synonyms(result["search_query"])

    return result


def web_research(state: SummaryState, config: RunnableConfig):
    """LangGraph node that performs web research using the generated search query."""
    configurable = Configuration.from_runnable_config(config)
    search_api = get_config_value(configurable.search_api)

    if search_api == "tavily":
        search_results = tavily_search(
            state.search_query,
            fetch_full_page=configurable.fetch_full_page,
            max_results=SEARCH_RESULTS_PER_LOOP,
        )
    elif search_api == "perplexity":
        search_results = perplexity_search(
            state.search_query, state.research_loop_count
        )
    elif search_api == "duckduckgo":
        # Паралельний пошук через ВСІ загальні пошукові системи (DuckDuckGo, Tavily, Bing, Google)
        search_results = parallel_search(
            state.search_query,
            max_results=SEARCH_RESULTS_PER_LOOP,
            fetch_full_page=configurable.fetch_full_page,
        )
    elif search_api == "searxng":
        search_results = searxng_search(
            state.search_query,
            max_results=SEARCH_RESULTS_PER_LOOP,
            fetch_full_page=configurable.fetch_full_page,
        )
    elif search_api == "pubmed":
        from ollama_deep_researcher.utils import pubmed_search
        search_results = pubmed_search(
            state.search_query,
            max_results=SEARCH_RESULTS_PER_LOOP,
        )
    else:
        raise ValueError(f"Unsupported search API: {configurable.search_api}")

    annotate_source_relevance(search_results, state.search_query)
    search_results["results"] = sorted(
        search_results.get("results", []),
        key=lambda s: s.get("relevance_score", 0.0),
        reverse=True,
    )
    assign_source_ids(search_results, start_index=len(state.source_details) + 1)
    search_str = deduplicate_and_format_sources(
        search_results,
        max_tokens_per_source=MAX_TOKENS_PER_SOURCE,
        fetch_full_page=configurable.fetch_full_page,
    )

    source_details = [
        {
            "id": source.get("source_id"),
            "title": source.get("title"),
            "url": source.get("url"),
            "snippet": source.get("content"),
            "fetched_at": source.get("fetched_at"),
            "content_chars": len(source.get("raw_content") or ""),
            "relevance_score": source.get("relevance_score", 0.0),
        }
        for source in search_results.get("results", [])
    ]

    return {
        "sources_gathered": [format_sources(search_results)],
        "source_details": source_details,
        "research_loop_count": state.research_loop_count + 1,
        "web_research_results": [search_str],
    }


def summarize_sources(state: SummaryState, config: RunnableConfig):
    """LangGraph node that summarizes web research results with deep analysis."""
    existing_summary = state.running_summary
    most_recent_web_research = state.web_research_results[-1]

    if existing_summary:
        human_message_content = (
            f"<Existing Summary> \n {existing_summary} \n <Existing Summary>\n\n"
            f"<New Context> \n {most_recent_web_research} \n <New Context>"
            f"Update the Existing Summary with the New Context. "
            f"Use ANALYSIS_FRAMEWORK: 1) Key facts 2) Comparisons 3) Trends 4) Contradictions 5) Conclusions. "
            f"Topic: \n <User Input> \n {state.research_topic} \n <User Input>\n\n"
        )
    else:
        human_message_content = (
            f"<Context> \n {most_recent_web_research} \n <Context>"
            f"Create a deep analytical Summary using the Context. "
            f"Use ANALYSIS_FRAMEWORK: 1) Key facts 2) Comparisons 3) Trends 4) Contradictions 5) Conclusions. "
            f"Topic: \n <User Input> \n {state.research_topic} \n <User Input>\n\n"
        )

    configurable = Configuration.from_runnable_config(config)

    if configurable.llm_provider == "lmstudio":
        llm = ChatLMStudio(
            base_url=configurable.lmstudio_base_url,
            model=configurable.dolphin_llm,  # Use dolphin for analysis
            temperature=0,
        )
    else:
        llm = LLMFactory.get_llm(
            model_name=configurable.dolphin_llm, # Use dolphin for analysis
            temperature=0,
            num_ctx=settings.context_size,
            num_gpu=-1,
            base_url=configurable.ollama_base_url,
        )

    result = llm.invoke(
        [
            SystemMessage(content=summarizer_instructions),
            HumanMessage(content=human_message_content),
        ]
    )

    running_summary = result.content
    logger.info("Raw LLM Summary Response (first 100 chars): %s", running_summary[:100].replace("\n", " "))
    if configurable.strip_thinking_tokens:
        running_summary = strip_thinking_tokens(running_summary)

    return {"running_summary": running_summary}


def reflect_on_summary(state: SummaryState, config: RunnableConfig):
    """LangGraph node that identifies knowledge gaps."""
    configurable = Configuration.from_runnable_config(config)
    formatted_prompt = reflection_instructions.format(
        research_topic=state.research_topic
    )

    @tool
    class FollowUpQuery(BaseModel):
        follow_up_query: str = Field(
            description="Write a specific question to address this gap"
        )
        knowledge_gap: str = Field(
            description="Describe what information is missing or needs clarification"
        )

    messages = [
        SystemMessage(
            content=formatted_prompt + (
                tool_calling_reflection_instructions if configurable.use_tool_calling 
                else json_mode_reflection_instructions
            )
        ),
        HumanMessage(
            content=f"Reflect on our existing knowledge: \n === \n {state.running_summary}, \n === \n And now identify a knowledge gap and generate a follow-up web search query:"
        ),
    ]

    result = generate_search_query_with_structured_output(
        configurable=configurable,
        messages=messages,
        tool_class=FollowUpQuery,
        fallback_query=f"Tell me more about {state.research_topic}",
        tool_query_field="follow_up_query",
        json_query_field="follow_up_query",
    )

    # Якщо reflection каже що даних достатньо — позначаємо це
    if result.get("search_query") == "COMPLETE":
        result["_complete"] = True

    return result


def finalize_summary(state: SummaryState):
    """LangGraph node that finalizes the research summary."""
    seen_sources = set()
    unique_sources = []

    for source in state.sources_gathered:
        for line in source.split("\n"):
            if line.strip() and line not in seen_sources:
                seen_sources.add(line)
                unique_sources.append(line)

    all_sources = "\n".join(unique_sources)
    state.running_summary = (
        f"## Summary\n{state.running_summary}\n\n ### Sources:\n{all_sources}"
    )
    return {"running_summary": state.running_summary}


def route_research(
    state: SummaryState, config: RunnableConfig
) -> Literal["finalize_summary", "web_research"]:
    """Adaptive routing: зупиняється раніше, якщо нової інформації не знайдено."""
    configurable = Configuration.from_runnable_config(config)

    # Адаптивне завершення:
    # 1. Якщо перевищено ліміт циклів
    if state.research_loop_count >= MAX_RESEARCH_LOOPS:
        return "finalize_summary"

    # 2. Якщо reflection позначив як COMPLETE (достатньо даних)
    if hasattr(state, 'search_query') and state.search_query == "COMPLETE":
        return "finalize_summary"

    # 3. Якщо користувач встановив менше циклів — дотримуємось
    max_loops = getattr(configurable, 'max_web_research_loops', MAX_RESEARCH_LOOPS)
    if state.research_loop_count >= max_loops:
        return "finalize_summary"

    return "web_research"


# Add nodes and edges
builder = StateGraph(
    SummaryState,
    input_schema=SummaryStateInput,
    output_schema=SummaryStateOutput,
    config_schema=Configuration,
)
builder.add_node("generate_query", generate_query)
builder.add_node("web_research", web_research)
builder.add_node("summarize_sources", summarize_sources)
builder.add_node("reflect_on_summary", reflect_on_summary)
builder.add_node("finalize_summary", finalize_summary)

builder.add_edge(START, "generate_query")
builder.add_edge("generate_query", "web_research")
builder.add_edge("web_research", "summarize_sources")
builder.add_edge("summarize_sources", "reflect_on_summary")
builder.add_conditional_edges("reflect_on_summary", route_research)
builder.add_edge("finalize_summary", END)

graph = builder.compile()
