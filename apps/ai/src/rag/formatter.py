"""引用候補（Citation 配列）を Claude 向けの Markdown ブロックに整形する。

このファイルが扱う AI 概念：

* **RAG injection の最終段** — retriever が返した結果を、Claude の system
  プロンプト末尾に追記する **Markdown ブロック** に成形する。
* **引用 ID の採番** — ``[1]``, ``[2]`` … と人間可読な連番を振り、
  プロンプト側の指示「引用末尾に [番号] を付与せよ」と対応させる。
  これによりモデルが回答中で引用したときに、UI 側で番号 → 出典 URL の
  逆引きができる。
* **取得日時の併記** — 法令は改正されるため「いつ取得した条文か」を残す。
  モデルにも「最新改正は別途確認するよう注意喚起する」よう促せる。
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from .retriever import Citation


def format_citations(citations: Iterable[Citation], today: date | None = None) -> str:
    """``Citation`` の配列を ``## 参考法令`` から始まる Markdown 文字列に整形。

    出力例（簡略化）::

        ## 参考法令（最新の e-Gov 法令データから検索）

        以下は本リクエストに関連すると思われる法令条文です。回答時は該当条文を引用し、
        引用末尾に [番号] を付してください。...

        [1] 民法（明治二十九年法律第八十九号）第415条（債務不履行による損害賠償）
        債務者がその債務の本旨に従った履行をしないとき...
        （出典: https://laws.e-gov.go.jp/.../ / 取得日: 2026-04-30）

        [2] ...

    Parameters
    ----------
    citations:
        retriever が返した順（= 関連度順）。順序を保ったまま採番する。
    today:
        テスト時に取得日を固定したい場合のための注入ポイント。本番では None。
    """
    cites = list(citations)
    if not cites:
        # 候補ゼロなら空文字を返す。呼び出し側はこれを見て system に
        # RAG ブロックを **追加しない** ことを判断できる。
        return ""

    fetched = (today or date.today()).isoformat()
    # ブロック先頭にメタ説明を入れる：モデルに「これは検索結果である」
    # 「引用ルールはこう」「データはこの時点のもの」を伝えるためのプリアンブル。
    lines: list[str] = [
        "## 参考法令（最新の e-Gov 法令データから検索）",
        "",
        "以下は本リクエストに関連すると思われる法令条文です。"
        "回答時は該当条文を引用し、引用末尾に [番号] を付してください。"
        "該当する法令がない場合はその旨を明示してください。"
        "取得日時点の e-Gov データに基づく内容のため、最新改正は別途ご確認ください。",
        "",
    ]
    # 1 始まりの連番を振る（[0] は人間慣習的に違和感があるため）。
    for idx, c in enumerate(cites, start=1):
        article = f"{c.article_no}" if c.article_no else ""
        if c.article_title:
            article = f"{article}（{c.article_title}）" if article else f"（{c.article_title}）"
        header = f"[{idx}] {c.law_title}（{c.law_num}）{article}".rstrip()
        lines.append(header)
        lines.append(c.body.strip())
        # 出典 URL と取得日を 1 行で添える：
        # - URL: モデルに「確かにこの条文は実在する」という根拠を見せる
        # - 取得日: 法令改正があった場合に「いつのスナップショットか」を保持
        lines.append(f"（出典: {c.source_url} / 取得日: {fetched}）")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
