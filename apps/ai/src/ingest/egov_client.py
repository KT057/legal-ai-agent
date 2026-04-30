"""e-Gov 法令 API v2 クライアント。

このファイルが扱う AI 概念：

* **API スロットリング** — e-Gov のような公共 API には事実上のレート制限がある。
  クライアント側でリクエスト間隔を 1 秒空けることで、429 で叩き返されるのを未然に防ぐ。
* **指数バックオフ・リトライ** — 429 / 5xx のような **一時的** な失敗には待って再試行、
  4xx (404 など) は **恒久的** な失敗として即時 raise。区別しないと永久に再試行で詰まる。
* **lazy import** — ``lxml`` は C 拡張で起動コストがある。テスト時に
  XML パースを通らないコードパス（chunker のユニットテスト等）では import を遅延させたい。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import settings


@dataclass(frozen=True, slots=True)
class FetchedLaw:
    """e-Gov から取得した法令データ。メタ情報 + 生 XML を持つ DTO。"""

    law_id: str
    law_num: str
    title: str
    law_type: str
    promulgation_date: str | None
    source_url: str
    raw_xml: str


class EgovClient:
    """e-Gov API v2 への薄い HTTP クライアント。``async with`` で使う。"""

    def __init__(self, base_url: str | None = None, request_interval_sec: float = 1.0) -> None:
        self._base = (base_url or settings.egov_api_base).rstrip("/")
        # スロットル間隔。1 秒間隔は経験則的に 429 を踏まないライン。
        self._interval = request_interval_sec
        self._client = httpx.AsyncClient(
            # 30 秒の全体タイムアウト + 10 秒の connect タイムアウト。
            # 法令 XML は数 MB になることがあり connect より read の方が長くなる。
            timeout=httpx.Timeout(30.0, connect=10.0),
            # User-Agent を明示するのは公共 API 利用のマナーかつ問い合わせ窓口。
            headers={"User-Agent": "legal-ai-agent/0.1 (+https://github.com/)"},
        )
        # 最後のリクエスト時刻（event loop 時間軸）。スロットル計算に使う。
        self._last_call: float = 0.0

    async def __aenter__(self) -> EgovClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        # コネクションを正しくクローズしないとファイルディスクリプタリークになる。
        await self._client.aclose()

    async def _throttle(self) -> None:
        """前回リクエストから ``_interval`` 経つまで sleep する。

        ``time.time()`` ではなく ``asyncio.get_event_loop().time()`` を使うのは、
        テストで loop を差し替えるときに「同じ時刻軸」で計算するため。
        """
        now = asyncio.get_event_loop().time()
        wait = self._interval - (now - self._last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call = asyncio.get_event_loop().time()

    async def _get(self, path: str, max_retries: int = 4) -> str:
        """指数バックオフ付き GET。

        - 200 → そのまま返す
        - 429 / 5xx → リトライ可能扱いで例外化（後段 except で吸収して再試行）
        - その他 4xx → ``raise_for_status`` で即時 raise（再試行しても直らない）
        - ネットワーク層の例外もリトライ対象（一時的な接続失敗を想定）

        待機は ``2**attempt`` 秒（1, 2, 4, 8...）。最後の試行でも失敗したら raise。
        """
        url = f"{self._base}{path}"
        for attempt in range(max_retries):
            await self._throttle()
            try:
                res = await self._client.get(url)
                if res.status_code == 200:
                    return res.text
                if res.status_code in (429, 500, 502, 503, 504):
                    # 一時的失敗を再試行ループに乗せるため例外化する。
                    raise httpx.HTTPStatusError(
                        f"retryable {res.status_code}", request=res.request, response=res
                    )
                # 上記以外の非 200（404 等）は恒久エラー扱いで即 raise。
                res.raise_for_status()
                return res.text
            except (httpx.HTTPStatusError, httpx.TransportError):
                # 最後の試行でもダメだったら例外を伝播させて呼び出し側に失敗を伝える。
                if attempt == max_retries - 1:
                    raise
                # 指数バックオフ: 1, 2, 4, 8 秒で再試行。
                await asyncio.sleep(2**attempt)
        # ループは必ず return か raise で抜けるはずなので、ここに来たら型ヒント補助。
        raise RuntimeError(f"unreachable: {url}")

    async def fetch_law(self, law_id: str) -> FetchedLaw:
        """e-Gov v2: ``GET /law_data/{law_id}`` → 法令本文 XML をメタ情報込みで返す。

        ``source_url`` は API ではなく **人間向けページ** の URL を入れる
        （引用 UI から「e-Gov でこの法令を開く」ボタンに使う想定）。
        """
        xml = await self._get(f"/law_data/{law_id}")
        meta = _parse_law_meta(xml, law_id)
        return FetchedLaw(
            law_id=law_id,
            law_num=meta["law_num"],
            title=meta["title"],
            law_type=meta["law_type"],
            promulgation_date=meta["promulgation_date"],
            source_url=f"https://laws.e-gov.go.jp/law/{law_id}",
            raw_xml=xml,
        )


def _parse_law_meta(xml: str, law_id: str) -> dict[str, Any]:
    """法令 XML からタイトル等のメタ情報を抽出する。Lazy import to keep test/import cost low.

    e-Gov 法令 XML の **最低限の構造**:
    - root 属性 ``LawType``: "法律" / "政令" / "省令" 等
    - root 属性 ``PromulgateDate``: 施行日 (YYYY-MM-DD)
    - 子要素 ``LawTitle``: 法令名（例: "民法"）
    - 子要素 ``LawNum``: 法令番号（例: "明治二十九年法律第八十九号"）
    """
    from lxml import etree  # type: ignore[import-untyped]

    try:
        root = etree.fromstring(xml.encode("utf-8"))
    except etree.XMLSyntaxError as exc:  # pragma: no cover
        raise ValueError(f"invalid law XML for {law_id}: {exc}") from exc

    # find は最初の一致を返す（None の可能性あり）。属性は dict ライクに引く。
    title_el = root.find(".//LawTitle")
    law_num_el = root.find(".//LawNum")
    law_type = root.attrib.get("LawType", "法律")
    promulgation = root.attrib.get("PromulgateDate")
    return {
        # title が取れない異常 XML では law_id をフォールバック表示にする。
        "title": (title_el.text or "").strip() if title_el is not None else law_id,
        "law_num": (law_num_el.text or "").strip() if law_num_el is not None else "",
        "law_type": law_type,
        "promulgation_date": promulgation,
    }
