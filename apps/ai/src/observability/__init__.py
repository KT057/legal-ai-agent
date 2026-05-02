"""Langfuse による LLM observability の薄いラッパ層。

外側からはこのパッケージ経由でだけ Langfuse に触る。
``settings.langfuse_tracing_enabled = False`` または API キーが空のときは
全関数が no-op になり、Langfuse 未起動でもアプリは平常動作する。
"""

from .langfuse_client import (
    flush_langfuse,
    get_langfuse,
    observe,
    traced_messages_create,
    tracing_enabled,
)

__all__ = [
    "flush_langfuse",
    "get_langfuse",
    "observe",
    "traced_messages_create",
    "tracing_enabled",
]
