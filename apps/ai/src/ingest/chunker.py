"""法令 XML を Article 単位でチャンク化する。

このファイルが扱う AI 概念：

* **チャンク粒度の選択** — RAG では「埋め込み 1 件 = 1 チャンク」になる。
  細かく切ると検索精度↑だが文脈不足、粗く切ると文脈は保てるが類似度が薄まる。
  日本の法令は ``<Article>`` 単位が天然のセマンティック境界なので採用。
* **トークン上限とスライディングウィンドウ** — 1 チャンクが ~800 トークンを
  超えると、埋め込みモデルの精度が落ちたりプロンプト膨張に響く。
  超える場合は ``_SPLIT_CHAR_WIDTH=600`` 字 / ``_SPLIT_OVERLAP=80`` 字の
  オーバーラップ付きで分割し、境界で文脈が切れないようにする。
* **ヘッダ除外** — ``<ArticleTitle>`` (条番号) や ``<ArticleCaption>`` (見出し)
  を本文に含めると「第○条」のような短文で類似度がノイジーになる。
  これらは別フィールド（``article_no`` / ``article_title``）に出して
  ``body`` には本文だけを残す。
* **トークン数の近似** — tiktoken は OpenAI 系のトークナイザだが、日本語でも
  ざっくり妥当な数が出る。利用不可な環境ではフォールバック式 ``len/2`` を使う
  （安全側に多めに見積もって過剰分割を起こす方向に倒す）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Chunk:
    """埋め込み対象の 1 単位。``body`` はヘッダを除いた本文。"""

    article_no: str | None
    article_title: str | None
    body: str
    token_count: int


# 1 チャンクが超えてはならない概算トークン数（embedding API の精度を保つ目安）。
_MAX_TOKENS_PER_CHUNK = 800
# 上限を超えた場合の分割幅（文字数ベース）。トークン数より字数で切るのが安全で速い。
_SPLIT_CHAR_WIDTH = 600
# 分割境界での文脈ロスを抑えるための重複量。
# 例：000-600, 520-1120, 1040-1640 のように 80 字ずつ前と被らせて切る。
_SPLIT_OVERLAP = 80


def _count_tokens(text: str) -> int:
    """Approximate token count. Uses tiktoken when available, falls back to len/2.

    Japanese ratio of chars-to-tokens with cl100k is ~1.3-1.8; len/2 is a rough
    upper bound that keeps chunking conservative without hard-failing on missing deps.

    日本語のトークン化は英語よりかなり細かい。実測では 1 字 ≒ 0.5〜0.8 トークン。
    tiktoken が無い環境では ``len/2`` で **多めに** 見積もり、結果的に過剰分割
    （= 安全側）に倒す。0 を返さないよう ``max(1, ...)`` でガード。
    """
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:  # pragma: no cover
        return max(1, len(text) // 2)


def _window_split(text: str, width: int, overlap: int) -> list[str]:
    """``width`` 字ごとに ``overlap`` 字オーバーラップさせながら分割する。

    インデックス計算のキモ:
    - 切り出しは ``[start, end)``、``end = start + width`` （末尾は文字列長で頭打ち）
    - 次の ``start`` は ``end - overlap``：オーバーラップぶん戻る
    - ``end == len(text)`` で終端に達したらループを抜ける（無限ループ防止）
    """
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

    フロー:
    1. ``root.iter("Article")`` で全ての ``<Article>`` を深さ優先で巡回
    2. ヘッダ要素（条番号・見出し）を別フィールドに分離して body から除外
    3. body が空 → スキップ（"削除" のような中身ゼロの条文を排除）
    4. トークン数が上限内 → そのまま 1 チャンク
    5. 上限超 → ``_window_split`` で複数チャンクに分割
    """
    from lxml import etree

    root = etree.fromstring(xml.encode("utf-8"))
    chunks: list[Chunk] = []

    for art in root.iter("Article"):
        # 条番号は ArticleTitle の text、なければ Num 属性をフォールバック。
        article_no = _text_of(art.find("ArticleTitle")) or art.attrib.get("Num")
        # 見出しは ArticleCaption（"第415条 債務不履行による損害賠償" の "債務不履行..." 部分）。
        caption = _text_of(art.find("ArticleCaption"))
        body = _body_text(art).strip()
        if not body:
            # 本文ゼロ（削除条等）は埋め込みしても意味がないのでスキップ。
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
        # 上限超：オーバーラップ付きスライディングウィンドウで分割。
        # 各 piece は同じ article_no / article_title を共有する（メタは保持）。
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


# 本文に含めたくないタグ群。frozenset で in 判定を高速化＆改変防止。
_HEADER_TAGS = frozenset({"ArticleTitle", "ArticleCaption"})


def _text_of(el):  # type: ignore[no-untyped-def]
    """要素内の全テキストを連結して返す。空なら None。

    ``itertext()`` は要素以下の全テキストノードを順に返すジェネレータ。
    ヘッダ要素には子要素 (Ruby 等) が混じることがあるためこちらを使う。
    """
    if el is None:
        return None
    text = "".join(el.itertext()).strip()
    return text or None


def _body_text(article):  # type: ignore[no-untyped-def]
    """Concatenate non-empty text nodes under Article, skipping header elements.

    XML 木探索のコツ:
    - ``article.iter()`` で配下の全ノードを順に走査
    - ``node.text`` = タグの直後・最初の子の前にあるテキスト
    - ``node.tail`` = タグの **閉じ** の直後、次の兄弟要素の前にあるテキスト
    - tail を取り損ねると本文に欠落が生まれるため両方拾う必要がある
    - ヘッダ要素自体と、その配下のテキストはまとめてスキップしないと
      条番号や見出しが本文に混入してしまう。
    """
    parts: list[str] = []
    for node in article.iter():
        if node.tag in _HEADER_TAGS:
            # ヘッダタグ自体は処理しない。配下は ``_has_header_ancestor`` で個別に弾く。
            continue
        # Only emit the .text of leaf-ish nodes; itertext is too greedy because
        # it would still pull text from header siblings via tail.
        if node.text and node.text.strip():
            # ``node`` がヘッダタグの子孫だったら本文に含めない。
            if _has_header_ancestor(node):
                continue
            parts.append(node.text.strip())
        if node.tail and node.tail.strip():
            # tail はヘッダの **直後** にぶら下がる本文ケースがあるため
            # 祖先チェックを入れず採用。ここを過剰に絞ると本文が抜ける。
            parts.append(node.tail.strip())
    return "\n".join(parts)


def _has_header_ancestor(node) -> bool:  # type: ignore[no-untyped-def]
    """``node`` の祖先連鎖の中に ``_HEADER_TAGS`` が含まれているか判定。

    XML の親をたどるユーティリティ。lxml の ``getparent()`` を None まで遡る
    シンプルな実装。深さは数段なので O(深さ) で問題にならない。
    """
    parent = node.getparent()
    while parent is not None:
        if parent.tag in _HEADER_TAGS:
            return True
        parent = parent.getparent()
    return False
