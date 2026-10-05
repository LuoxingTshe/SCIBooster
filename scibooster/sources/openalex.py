"""OpenAlex wrapper (built on pyalex): DOI/title matching, abstracts, references, citing works, fallback search."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

import pyalex
from pyalex import Works, invert_abstract

from ..config import Settings, get_settings
from ..models import Origin, Paper
from ..store import normalize_doi, short_oa_id
from ..trace import NULL_TRACER, Tracer
from .cache import NO_CACHE, Cache

FIELDS = [
    "id", "doi", "title", "publication_year", "authorships", "primary_location",
    "abstract_inverted_index", "cited_by_count", "referenced_works", "keywords", "type", "is_retracted",
]
BATCH = 50


class OpenAlexClient:
    def __init__(self, settings: Settings | None = None, cache: Cache = NO_CACHE, tracer: Tracer = NULL_TRACER):
        s = settings or get_settings()
        if s.openalex_email:
            pyalex.config.email = s.openalex_email
        if s.openalex_api_key:
            pyalex.config.api_key = s.openalex_api_key
        pyalex.config.max_retries = 3
        pyalex.config.retry_backoff_factor = 0.5
        self.cache = cache
        self.tracer = tracer

    # ---- low level: one request = one cache entry ----
    def _fetch(self, query, per_page: int = 50) -> list[dict]:
        url = query.url
        key = Cache.key("openalex", url, per_page)
        if (hit := self.cache.get(key)) is not None:
            return hit
        res = query.get(per_page=per_page)
        rows = [dict(r) for r in res]
        self.tracer.usage.openalex_requests += 1
        self.tracer.log("openalex", url=url, n=len(rows))
        self.cache.set(key, rows)
        return rows

    # ---- lookups ----
    def by_ids(self, ids: list[str], origin: Origin = "backward", hop: int = 0) -> list[Paper]:
        ids = list(dict.fromkeys(short_oa_id(i) for i in ids if i))
        out: list[Paper] = []
        for i in range(0, len(ids), BATCH):
            chunk = ids[i : i + BATCH]
            rows = self._fetch(Works().filter(openalex_id="|".join(chunk)).select(FIELDS), per_page=len(chunk))
            out += [to_paper(r, origin, hop) for r in rows]
        return out

    def by_id(self, oa_id: str, origin: Origin = "agent") -> Paper | None:
        res = self.by_ids([oa_id], origin=origin)
        return res[0] if res else None

    def by_dois(self, dois: list[str], origin: Origin = "wos_search", hop: int = 0) -> dict[str, Paper]:
        dois = list(dict.fromkeys(d for d in (normalize_doi(x) for x in dois) if d))
        out: dict[str, Paper] = {}
        for i in range(0, len(dois), BATCH):
            chunk = dois[i : i + BATCH]
            rows = self._fetch(Works().filter(doi="|".join(chunk)).select(FIELDS), per_page=len(chunk))
            for r in rows:
                p = to_paper(r, origin, hop)
                if p.doi:
                    out[p.doi] = p
        return out

    def by_title(self, title: str, min_sim: float = 0.9, origin: Origin = "seed") -> Paper | None:
        """Exact title match. OpenAlex years are sometimes wrong (reprints/repository copies), so no year filter;
        among candidates with similarity >= min_sim, take the most cited (usually the canonical record)."""
        q = Works().search_filter(title=_strip_for_search(title)).select(FIELDS)
        cands = [r for r in self._fetch(q, per_page=25) if title_similarity(title, r.get("title") or "") >= min_sim]
        if not cands:
            return None
        return to_paper(max(cands, key=lambda r: r.get("cited_by_count") or 0), origin)

    def search(self, query: str, *, years: tuple[int | None, int | None] = (None, None), limit: int = 50,
               origin: Origin = "openalex_search") -> list[Paper]:
        q = Works().search(query).select(FIELDS)
        y0, y1 = years
        if y0 or y1:
            q = q.filter(publication_year=f"{y0 or ''}-{y1 or ''}")
        return [to_paper(r, origin) for r in self._fetch(q, per_page=min(limit, 200))]

    def citing(self, oa_id: str, limit: int = 25, hop: int = 1) -> list[Paper]:
        """Forward: works that cite oa_id, by citation count descending."""
        q = Works().filter(cites=short_oa_id(oa_id)).sort(cited_by_count="desc").select(FIELDS)
        return [to_paper(r, "forward", hop) for r in self._fetch(q, per_page=min(limit, 200))]

    def references(self, paper: Paper, limit: int = 25, hop: int = 1) -> list[Paper]:
        """Backward: works referenced by paper, keeping the limit most-cited."""
        refs = self.by_ids(paper.referenced_works, origin="backward", hop=hop)
        refs.sort(key=lambda p: -(p.cited_by_count or 0))
        return refs[:limit]


def to_paper(r: dict, origin: Origin = "wos_search", hop: int = 0) -> Paper:
    loc = r.get("primary_location") or {}
    src = loc.get("source") or {}
    inv = r.get("abstract_inverted_index")
    return Paper(
        id=short_oa_id(r["id"]),
        doi=normalize_doi(r.get("doi")),
        title=r.get("title") or "",
        authors=[(a.get("author") or {}).get("display_name") or "" for a in r.get("authorships") or []][:30],
        year=r.get("publication_year"),
        venue=src.get("display_name"),
        abstract=invert_abstract(inv) if inv else None,
        keywords=[k.get("display_name") for k in r.get("keywords") or [] if k.get("display_name")],
        cited_by_count=r.get("cited_by_count"),
        referenced_works=[short_oa_id(x) for x in r.get("referenced_works") or []],
        origin=origin,
        hop=hop,
        is_seed=origin == "seed",
        retracted=bool(r.get("is_retracted")),
    )


def _norm_title(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def title_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm_title(a), _norm_title(b)).ratio()


def _strip_for_search(t: str) -> str:
    # Commas/colons in an OpenAlex filter value get misparsed, so strip them
    return re.sub(r"[,:;|]", " ", t)
