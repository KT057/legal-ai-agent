"""PDF テキスト抽出ユーティリティ。

契約書 PDF からテキスト埋め込み層を抜き出して、既存のテキストパイプラインに合流させる。
スキャン PDF（画像のみ）は ``extract_text()`` で空文字が返るため、呼び出し側で
``ValueError`` として扱えるよう正規化する。OCR は将来課題。
"""

from __future__ import annotations

import io
import logging

from pypdf import PdfReader
from pypdf.errors import PdfReadError

LOG = logging.getLogger(__name__)


def extract_text(buf: bytes) -> str:
    """PDF バイト列からテキストを抽出する。

    - 各ページの ``extract_text()`` を改行で連結
    - 空白のみの行は捨てて圧縮
    - パース不能 / テキストゼロは ``ValueError``

    呼び出し側はこの ValueError を 400 にマップする想定。
    """
    if not buf:
        raise ValueError("empty PDF buffer")
    try:
        reader = PdfReader(io.BytesIO(buf))
    except PdfReadError as exc:
        raise ValueError(f"invalid PDF: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 — pypdf の例外は多岐
        raise ValueError(f"failed to open PDF: {exc}") from exc

    pages: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            LOG.warning("pypdf extract_text failed on page %d: %s", i, exc)
            text = ""
        # 行単位で空白圧縮（PDF 由来のソフト改行や余分なスペースを軽く整える）
        cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if cleaned:
            pages.append(cleaned)

    if not pages:
        raise ValueError("no extractable text in PDF (scanned image PDF?)")
    return "\n\n".join(pages)
