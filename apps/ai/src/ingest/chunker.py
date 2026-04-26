from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Chunk:
    article_no: str | None
    article_title: str | None
    body: str
    token_count: int


_MAX_TOKENS_PER_CHUNK = 800
_SPLIT_CHAR_WIDTH = 600
_SPLIT_OVERLAP = 80


def _count_tokens(text: str) -> int:
    """Approximate token count. Uses tiktoken when available, falls back to len/2.

    Japanese ratio of chars-to-tokens with cl100k is ~1.3-1.8; len/2 is a rough
    upper bound that keeps chunking conservative without hard-failing on missing deps.
    """
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:  # pragma: no cover
        return max(1, len(text) // 2)


def _window_split(text: str, width: int, overlap: int) -> list[str]:
    if len(text) <= width:
        return [text]
    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + width, len(text))
        out.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return out


def chunk_law(xml: str) -> list[Chunk]:
    """Walk e-Gov 法令 XML and emit one Chunk per <Article>, splitting long ones.

    The article header (ArticleTitle, ArticleCaption) is excluded from `body`
    so that articles consisting only of a title (e.g. 削除) are filtered out.
    """
    from lxml import etree

    root = etree.fromstring(xml.encode("utf-8"))
    chunks: list[Chunk] = []

    for art in root.iter("Article"):
        article_no = _text_of(art.find("ArticleTitle")) or art.attrib.get("Num")
        caption = _text_of(art.find("ArticleCaption"))
        body = _body_text(art).strip()
        if not body:
            continue
        tokens = _count_tokens(body)
        if tokens <= _MAX_TOKENS_PER_CHUNK:
            chunks.append(
                Chunk(
                    article_no=article_no,
                    article_title=caption,
                    body=body,
                    token_count=tokens,
                )
            )
            continue
        for piece in _window_split(body, _SPLIT_CHAR_WIDTH, _SPLIT_OVERLAP):
            chunks.append(
                Chunk(
                    article_no=article_no,
                    article_title=caption,
                    body=piece,
                    token_count=_count_tokens(piece),
                )
            )
    return chunks


_HEADER_TAGS = frozenset({"ArticleTitle", "ArticleCaption"})


def _text_of(el):  # type: ignore[no-untyped-def]
    if el is None:
        return None
    text = "".join(el.itertext()).strip()
    return text or None


def _body_text(article):  # type: ignore[no-untyped-def]
    """Concatenate non-empty text nodes under Article, skipping header elements."""
    parts: list[str] = []
    for node in article.iter():
        if node.tag in _HEADER_TAGS:
            # skip the entire subtree by clearing local text contributions
            continue
        # Only emit the .text of leaf-ish nodes; itertext is too greedy because
        # it would still pull text from header siblings via tail.
        if node.text and node.text.strip():
            # Skip if this node is a descendant of a header tag.
            if _has_header_ancestor(node):
                continue
            parts.append(node.text.strip())
        if node.tail and node.tail.strip():
            parts.append(node.tail.strip())
    return "\n".join(parts)


def _has_header_ancestor(node) -> bool:  # type: ignore[no-untyped-def]
    parent = node.getparent()
    while parent is not None:
        if parent.tag in _HEADER_TAGS:
            return True
        parent = parent.getparent()
    return False
