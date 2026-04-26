"""Shared test setup: stub required envs before src.config is imported."""
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("VOYAGE_API_KEY", "test-voyage-key")
os.environ.setdefault("RAG_ENABLED", "false")
