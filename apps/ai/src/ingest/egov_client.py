from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import settings


@dataclass(frozen=True, slots=True)
class FetchedLaw:
    law_id: str
    law_num: str
    title: str
    law_type: str
    promulgation_date: str | None
    source_url: str
    raw_xml: str


class EgovClient:
    def __init__(self, base_url: str | None = None, request_interval_sec: float = 1.0) -> None:
        self._base = (base_url or settings.egov_api_base).rstrip("/")
        self._interval = request_interval_sec
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": "legal-ai-agent/0.1 (+https://github.com/)"},
        )
        self._last_call: float = 0.0

    async def __aenter__(self) -> EgovClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._client.aclose()

    async def _throttle(self) -> None:
        now = asyncio.get_event_loop().time()
        wait = self._interval - (now - self._last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call = asyncio.get_event_loop().time()

    async def _get(self, path: str, max_retries: int = 4) -> str:
        url = f"{self._base}{path}"
        for attempt in range(max_retries):
            await self._throttle()
            try:
                res = await self._client.get(url)
                if res.status_code == 200:
                    return res.text
                if res.status_code in (429, 500, 502, 503, 504):
                    raise httpx.HTTPStatusError(
                        f"retryable {res.status_code}", request=res.request, response=res
                    )
                res.raise_for_status()
                return res.text
            except (httpx.HTTPStatusError, httpx.TransportError):
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2**attempt)
        raise RuntimeError(f"unreachable: {url}")

    async def fetch_law(self, law_id: str) -> FetchedLaw:
        """e-Gov v2: GET /law_data/{law_id} → 法令本文 XML."""
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
    """Lazy import to keep test/import cost low."""
    from lxml import etree  # type: ignore[import-untyped]

    try:
        root = etree.fromstring(xml.encode("utf-8"))
    except etree.XMLSyntaxError as exc:  # pragma: no cover
        raise ValueError(f"invalid law XML for {law_id}: {exc}") from exc

    title_el = root.find(".//LawTitle")
    law_num_el = root.find(".//LawNum")
    law_type = root.attrib.get("LawType", "法律")
    promulgation = root.attrib.get("PromulgateDate")
    return {
        "title": (title_el.text or "").strip() if title_el is not None else law_id,
        "law_num": (law_num_el.text or "").strip() if law_num_el is not None else "",
        "law_type": law_type,
        "promulgation_date": promulgation,
    }
