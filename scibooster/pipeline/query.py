"""Research intent -> search queries (WoS advanced query / OpenAlex search) and execution."""

from __future__ import annotations

import json
import math
import re

from ..llm import prompts as P
from ..llm.deepseek import LLM
from ..models import Paper, ResearchIntent
from ..sources.openalex import OpenAlexClient
from ..sources.wos import MAX_LIMIT, WosBudgetExceeded, WosClient, WosQueryError
from ..trace import NULL_TRACER, Tracer


def build_wos_queries(intent: ResearchIntent, llm: LLM, n: int = 3) -> list[str]:
    data = llm.chat_json(
        P.fill(P.QUERY_SYSTEM, n=n),
        P.fill(P.QUERY_USER, intent=intent.model_dump_json(indent=1)),
        purpose="wos_query",
    )
    qs = [q.strip() for q in data.get("queries") or [] if isinstance(q, str) and q.strip()]
    qs = [ensure_year_clause(strip_acronym_truncation(q), intent.year_range) for q in qs[:n]]
    return qs or [fallback_wos_query(intent)]


def ensure_year_clause(q: str, years: tuple[int | None, int | None]) -> str:
    y0, y1 = years
    if (y0 is None and y1 is None) or re.search(r"\bPY\s*=", q, re.I):
        return q
    return f"({q}) AND PY=({y0 or 1900}-{y1 or 2100})"


_ACRONYM_TRUNC = re.compile(r'"([A-Z][A-Z0-9-]{1,5})\*"')


def strip_acronym_truncation(q: str) -> str:
    """Drop * after short all-caps acronyms: in WoS "GAT*" also matches gate/gather (947 vs 52 hits in a live test)."""
    return _ACRONYM_TRUNC.sub(r'"\1"', q)


def fallback_wos_query(intent: ResearchIntent) -> str:
    """Deterministic fallback when the LLM returns nothing usable: AND across concept facets, OR within each facet's synonyms."""
    facets = []
    for c in intent.core_concepts or intent.keywords_en[:2]:
        terms = [c, *intent.synonyms.get(c, [])][:4]
        facets.append("(" + " OR ".join(f'"{t}"' for t in terms) + ")")
    return ensure_year_clause("TS=(" + " AND ".join(facets) + ")", intent.year_range)


def fix_wos_query(query: str, error: str, llm: LLM) -> str | None:
    data = llm.chat_json(
        P.fill(P.QUERY_SYSTEM, n=1), P.fill(P.QUERY_FIX_USER, query=query, error=error), purpose="wos_query_fix"
    )
    q = data.get("query")
    return strip_acronym_truncation(q.strip()) if isinstance(q, str) and q.strip() else None


def run_wos_queries(
    queries: list[str], wos: WosClient, llm: LLM, per_query: int, tracer: Tracer = NULL_TRACER
) -> tuple[list[str], list[Paper], list[str]]:
    """Returns (queries actually executed, hits, warnings). Each query gets one LLM fix-up attempt on a syntax error.

    per_query counts new papers only: queries overlap heavily when all are sorted by times cited, so later queries
    page past hits that earlier ones already returned (up to 3x per_query hits read per query).
    """
    executed: list[str] = []
    hits: list[Paper] = []
    warnings: list[str] = []
    seen: set[str] = set()
    max_pages = math.ceil(3 * per_query / MAX_LIMIT)
    for q in queries:
        for attempt in range(2):
            try:
                total, res = wos.search_all(q, max_results=per_query, seen=seen, max_pages=max_pages)
                executed.append(q)
                hits.extend(res)
                tracer.log("wos_query", query=q, total=total, got=len(res))
                break
            except WosQueryError as e:
                if attempt == 1 or not (fixed := fix_wos_query(q, e.message, llm)):
                    warnings.append(f"query failed: {q} ({e.message})")
                    break
                warnings.append(f"query rewritten: {q} -> {fixed}")
                q = fixed
            except WosBudgetExceeded as e:
                warnings.append(str(e))
                return executed, hits, warnings
    return executed, hits, warnings


def build_openalex_queries(intent: ResearchIntent) -> list[str]:
    """OpenAlex search supports AND/OR/quoted phrases; build one precise query plus one natural-language topic query."""
    facets = []
    for c in intent.core_concepts[:3]:
        terms = [c, *[s.rstrip("*") for s in intent.synonyms.get(c, [])]][:3]
        facets.append("(" + " OR ".join(f'"{t}"' for t in terms) + ")")
    qs = [" AND ".join(facets)] if facets else []
    qs.append(intent.topic)
    return qs


def run_openalex_queries(
    queries: list[str], oa: OpenAlexClient, intent: ResearchIntent, per_query: int
) -> tuple[list[str], list[Paper], list[str]]:
    executed, hits, warnings = [], [], []
    for q in queries:
        try:
            hits += oa.search(q, years=intent.year_range, limit=per_query)
            executed.append(q)
        except Exception as e:  # noqa: BLE001 - pyalex raises a mix of exception types; don't abort the build
            warnings.append(f"OpenAlex query failed: {q} ({e})")
    return executed, hits, warnings


def dumps_intent(intent: ResearchIntent) -> str:
    return json.dumps(intent.model_dump(), ensure_ascii=False, indent=2)
