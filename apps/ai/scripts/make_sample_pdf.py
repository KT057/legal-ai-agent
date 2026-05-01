"""契約書レビュー機能の動作確認用に、サンプル NDA PDF を生成するスクリプト。

reportlab は本番依存ではなく、このスクリプト専用なので uv の --with で一時注入する想定:

    uv run --with reportlab python scripts/make_sample_pdf.py

出力先: scripts/sample_nda.pdf
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent / "sample_nda.pdf"

# reportlab 同梱の日本語 CID フォント（追加ファイル不要）。
FONT_NAME = "HeiseiKakuGo-W5"

CONTRACT_TITLE = "秘密保持契約書（サンプル）"

CLAUSES: list[tuple[str, str]] = [
    (
        "第1条（目的）",
        "甲及び乙は、両者間の取引に関して開示される秘密情報の取扱いについて、本契約を締結する。",
    ),
    (
        "第2条（秘密情報の定義）",
        "本契約において「秘密情報」とは、書面・口頭・電磁的記録その他形式の如何を問わず、相手方から開示された一切の情報をいう。ただし、開示時点で既に公知のものはこの限りでない。",
    ),
    (
        "第3条（秘密保持義務）",
        "甲及び乙は、相手方の事前の書面による同意なく、秘密情報を第三者に開示・漏洩してはならない。また、本契約の目的以外に使用してはならない。",
    ),
    (
        "第4条（損害賠償）",
        "本契約に違反した当事者は、相手方に生じた一切の損害を賠償する責任を負う。賠償額の上限は設けないものとする。",
    ),
    (
        "第5条（有効期間）",
        "本契約の有効期間は、契約締結日から無期限とする。契約終了後も秘密保持義務は存続する。",
    ),
    (
        "第6条（準拠法及び合意管轄）",
        "本契約の準拠法は日本法とし、本契約に関連して生じる一切の紛争については、東京地方裁判所を第一審の専属的合意管轄裁判所とする。",
    ),
]


def _wrap(c: canvas.Canvas, text: str, x: float, y: float, max_width: float, leading: float) -> float:
    """日本語の横書きを max_width で折り返して描画。次の y を返す。"""
    line = ""
    for ch in text:
        if c.stringWidth(line + ch, FONT_NAME, 11) > max_width:
            c.drawString(x, y, line)
            y -= leading
            line = ch
        else:
            line += ch
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


def main() -> None:
    pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))

    c = canvas.Canvas(str(OUT), pagesize=A4)
    width, height = A4
    margin = 50
    max_width = width - margin * 2

    c.setFont(FONT_NAME, 18)
    c.drawCentredString(width / 2, height - margin, CONTRACT_TITLE)

    y = height - margin - 40
    c.setFont(FONT_NAME, 11)
    y = _wrap(
        c,
        "株式会社ABC（以下「甲」という）と株式会社XYZ（以下「乙」という）は、以下のとおり契約を締結する。",
        margin,
        y,
        max_width,
        18,
    )
    y -= 12

    for heading, body in CLAUSES:
        c.setFont(FONT_NAME, 12)
        c.drawString(margin, y, heading)
        y -= 18
        c.setFont(FONT_NAME, 11)
        y = _wrap(c, body, margin, y, max_width, 18)
        y -= 12
        if y < margin + 60:
            c.showPage()
            c.setFont(FONT_NAME, 11)
            y = height - margin

    c.setFont(FONT_NAME, 11)
    c.drawString(margin, y - 20, "甲: 株式会社ABC  代表取締役  山田 太郎")
    c.drawString(margin, y - 40, "乙: 株式会社XYZ  代表取締役  佐藤 花子")

    c.showPage()
    c.save()
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
