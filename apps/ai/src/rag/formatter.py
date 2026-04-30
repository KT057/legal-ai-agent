from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from .retriever import Citation


def format_citations(citations: Iterable[Citation], today: date | None = None) -> str:
    cites = list(citations)
    if not cites:
        return ""

    fetched = (today or date.today()).isoformat()
    lines: list[str] = [
        "## 参考法令（最新の e-Gov 法令データから検索）",
        "",
        "以下は本リクエストに関連すると思われる法令条文です。"
        "回答時は該当条文を引用し、引用末尾に [番号] を付してください。"
        "該当する法令がない場合はその旨を明示してください。"
        "取得日時点の e-Gov データに基づく内容のため、最新改正は別途ご確認ください。",
        "",
    ]
    for idx, c in enumerate(cites, start=1):
        article = f"{c.article_no}" if c.article_no else ""
        if c.article_title:
            article = f"{article}（{c.article_title}）" if article else f"（{c.article_title}）"
        header = f"[{idx}] {c.law_title}（{c.law_num}）{article}".rstrip()
        lines.append(header)
        lines.append(c.body.strip())
        lines.append(f"（出典: {c.source_url} / 取得日: {fetched}）")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
