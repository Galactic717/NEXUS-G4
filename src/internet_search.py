"""
Internet Search Entry Point.

This module provides a clean interface for the internet research capabilities
of the Deep Researcher PRO system. It encapsulates the complex orchestration
of parallel search providers, content fetching, and AI-driven synthesis.
"""

from .internet_block import internet_research, internet_research_stream, InternetResearchResult

__all__ = ["internet_research", "internet_research_stream", "InternetResearchResult"]
