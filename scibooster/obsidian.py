"""Obsidian vault export: one note per paper + a Base (table views) + a Canvas (year-layered citation DAG) + an overview.

Layout of the output folder (open it as a vault, or write it into an existing vault with vault_root):
    总览.md            overview: need, intent, queries, PRISMA flow (mermaid), embedded Base, link to the Canvas
    文献库.base         Obsidian Bases table views over the paper notes' properties (Obsidian >= 1.9)
    引用图谱.canvas     JSON Canvas 1.0: one row band per year (older on top), edges citing -> cited with relation labels
    papers/*.md        properties (frontmatter) + abstract + typed citation links

Links are written as vault-relative paths ([[sub/folder/papers/Name|Alias]]) so they stay unambiguous when several runs
share one vault. Everything after NOTES_MARKER in a note is user-owned and survives re-export.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .models import Corpus, Paper, Prisma

NOTES_MARKER = "%% scibooster:notes — 此行以下的内容在重新导出时保留 %%"
DEFAULT_NOTES = "\n## 我的笔记\n\n"
PAPERS_DIR = "papers"
OVERVIEW, BASE, CANVAS = "总览.md", "文献库.base", "引用图谱.canvas"

ORIGIN_NAMES = {
    "seed": "种子文献", "wos_search": "WoS 检索", "openalex_search": "OpenAlex 检索", "backward": "后向扩展（参考文献）",
    "forward": "前向扩展（施引文献）", "cocited": "共被引补缺", "agent": "Agent 添加",
}
RELATION_NAMES = {
    "extends": "扩展/改进", "uses_method": "使用方法", "uses_data": "使用数据", "compares": "对比", "critiques": "质疑",
    "background": "背景引用",
}
# Canvas colors: presets "1"-"6" follow the user's theme; hex for the rest (same hues as the dev renderer)
ORIGIN_COLORS = {"seed": "3", "openalex_search": "5", "wos_search": "5", "backward": "4", "forward": "6",
                 "cocited": "2", "agent": "#e07a2f"}
RETRACTED_COLOR = "1"
RELATION_COLORS = {"extends": "#e0457b", "uses_method": "#2a9d8f", "uses_data": "#3a86ff", "compares": "#f4a261",
                   "critiques": "#d62828"}

# Canvas geometry (px)
NODE_W, NODE_H, H_GAP, V_GAP = 320, 150, 40, 40
PER_LINE = 10  # wrap a year's row after this many papers
GROUP_PAD, GROUP_GAP = 40, 120


@dataclass
class VaultReport:
    out_dir: Path
    notes_written: int = 0
    notes_kept_user_text: int = 0  # existing notes whose user section was carried over
    stale_removed: list[str] = field(default_factory=list)
    stale_kept: list[str] = field(default_factory=list)  # no longer in the corpus but holding user notes


# ---------- naming / links ----------
_BAD_CHARS = re.compile(r'[\\/:*?"<>|#^\[\]]+')


def _first_author_last(p: Paper) -> str:
    if not p.authors or not p.authors[0].strip():
        return "Anon"
    return p.authors[0].split()[-1]


def short_label(p: Paper) -> str:
    return f"{_first_author_last(p)} {p.year or 'n.d.'}"


def note_names(papers: list[Paper], maxlen: int = 90) -> dict[str, str]:
    """paper id -> note basename (no extension), unique within the export."""
    names: dict[str, str] = {}
    used: set[str] = set()
    for p in papers:
        base = _BAD_CHARS.sub(" ", f"{short_label(p)} - {p.title or p.id}")
        base = re.sub(r"\s+", " ", base).strip(" .")[:maxlen].rstrip(" .")
        name = base if base.lower() not in used else f"{base} ({p.id})"
        used.add(name.lower())
        names[p.id] = name
    return names


def _yaml_str(s: str) -> str:
    # JSON string literals are valid YAML double-quoted scalars
    return json.dumps(s, ensure_ascii=False)


def _yaml_sq(s: str) -> str:
    """YAML single-quoted scalar: the form Bases filters use, since expressions contain double quotes."""
    return "'" + s.replace("'", "''") + "'"


def _yaml_list(key: str, items: list[str]) -> list[str]:
    if not items:
        return []
    return [f"{key}:"] + [f"  - {_yaml_str(i)}" for i in items]


# ---------- export ----------
def export_vault(corpus: Corpus, out_dir: Path, vault_root: Path | None = None) -> VaultReport:
    out_dir = Path(out_dir)
    vault_root = Path(vault_root) if vault_root else out_dir
    rel = out_dir.resolve().relative_to(vault_root.resolve()).as_posix()
    prefix = "" if rel == "." else rel + "/"
    papers_dir = out_dir / PAPERS_DIR
    papers_dir.mkdir(parents=True, exist_ok=True)

    names = note_names(corpus.papers)
    by_id = {p.id: p for p in corpus.papers}

    def link(pid: str) -> str:
        return f"[[{prefix}{PAPERS_DIR}/{names[pid]}|{short_label(by_id[pid])}]]"

    out_edges: dict[str, list] = defaultdict(list)
    indeg: Counter[str] = Counter()
    for e in corpus.edges:
        if e.source in by_id and e.target in by_id:
            out_edges[e.source].append(e)
            indeg[e.target] += 1

    report = VaultReport(out_dir=out_dir)
    for p in corpus.papers:
        path = papers_dir / f"{names[p.id]}.md"
        user_text = _user_section(path)
        if user_text is not None and user_text.strip() not in ("", DEFAULT_NOTES.strip()):
            report.notes_kept_user_text += 1
        path.write_text(_paper_note(p, out_edges[p.id], indeg[p.id], link) + (user_text or DEFAULT_NOTES),
                        encoding="utf-8")
        report.notes_written += 1

    current = {f"{n}.md" for n in names.values()}
    for f in sorted(papers_dir.glob("*.md")):
        if f.name in current or not _is_generated(f):
            continue
        user_text = _user_section(f) or ""
        if user_text.strip() in ("", DEFAULT_NOTES.strip()):
            f.unlink()
            report.stale_removed.append(f.name)
        else:
            report.stale_kept.append(f.name)

    (out_dir / BASE).write_text(_base_file(prefix), encoding="utf-8")
    (out_dir / CANVAS).write_text(
        json.dumps(_canvas(corpus, names, indeg, prefix), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    overview = out_dir / OVERVIEW
    overview_user = _user_section(overview)
    overview.write_text(_overview(corpus, indeg, link, prefix) + (overview_user or "\n## 笔记\n\n"), encoding="utf-8")
    return report


def _user_section(path: Path) -> str | None:
    """Text after NOTES_MARKER (including the leading newline), or None if the file/marker is absent."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    i = text.find(NOTES_MARKER)
    return None if i < 0 else text[i + len(NOTES_MARKER):]


def _is_generated(path: Path) -> bool:
    head = path.read_text(encoding="utf-8")[:400]
    return head.startswith("---\n") and "\nscibooster: true\n" in head


# ---------- paper note ----------
def _paper_note(p: Paper, edges: list, corpus_cites: int, link) -> str:
    r = p.relevance
    fm = ["---", "scibooster: true", f"title: {_yaml_str(p.title)}"]
    fm += _yaml_list("authors", p.authors)
    if p.year:
        fm.append(f"year: {p.year}")
    if p.venue:
        fm.append(f"venue: {_yaml_str(p.venue)}")
    if p.doi:
        fm += [f"doi: {_yaml_str(p.doi)}", f"url: {_yaml_str('https://doi.org/' + p.doi)}"]
    fm.append(f"paper_id: {_yaml_str(p.id)}")
    if r:
        fm += [f"relevance: {r.score:g}", f"relevance_reason: {_yaml_str(r.reason)}"]
        if r.flag:
            fm.append(f"relevance_flag: {_yaml_str(r.flag)}")
    fm += [f"origin: {p.origin}", f"hop: {p.hop}", f"seed: {str(p.is_seed).lower()}",
           f"retracted: {str(p.retracted).lower()}"]
    if p.cited_by_count is not None:
        fm.append(f"cited_by_count: {p.cited_by_count}")
    if p.wos_times_cited is not None:
        fm.append(f"wos_times_cited: {p.wos_times_cited}")
    fm.append(f"corpus_cites: {corpus_cites}")
    tags = ["scibooster/paper", f"scibooster/origin/{p.origin}"]
    if p.is_seed:
        tags.append("scibooster/seed")
    if p.retracted:
        tags.append("scibooster/retracted")
    fm += _yaml_list("tags", tags)
    fm += _yaml_list("cites", [link(e.target) for e in edges])
    # Typed citation links (one list property per relation label) for Bases columns and typed-link graph plugins
    typed: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e.relation:
            typed[e.relation.label].append(link(e.target))
    for label in RELATION_NAMES:
        fm += _yaml_list(label, typed.get(label, []))
    fm.append("---")

    body = [f"# {p.title or p.id}", ""]
    if p.retracted:
        body += ["> [!danger] 已撤稿", "> OpenAlex 将这篇文献标记为已撤稿。", ""]
    meta = ", ".join(p.authors[:8]) + (" 等" if len(p.authors) > 8 else "")
    links = []
    if p.doi:
        links.append(f"[DOI](https://doi.org/{p.doi})")
    if re.fullmatch(r"W\d+", p.id):
        links.append(f"[OpenAlex](https://openalex.org/{p.id})")
    body += [meta, f"*{p.venue or '—'}* · {p.year or 'n.d.'}" + (" · " + " · ".join(links) if links else ""), ""]
    if r:
        flag = "（无摘要，仅凭标题评分）" if r.flag == "no_abstract" else ""
        body += [f"**相关度 {r.score:g}/10**{flag}：{r.reason}", ""]
    body += ["> [!abstract] 摘要"]
    body += [f"> {line}" if line else ">" for line in (p.abstract or "（无摘要）").splitlines()]
    body.append("")
    if edges:
        body += [f"## 引用了库内 {len(edges)} 篇", ""]
        for e in edges:
            rel = f" — {RELATION_NAMES.get(e.relation.label, e.relation.label)}：{e.relation.rationale}" if e.relation else ""
            body.append(f"- {link(e.target)}{rel}")
        body.append("")
    body.append(f"被库内 {corpus_cites} 篇引用（见反向链接面板）；外部另有 {p.external_cited_by} 次被引。")
    if p.notes:
        body += ["", "## 检索备注", ""] + [f"- {n}" for n in p.notes]
    body += ["", NOTES_MARKER]
    return "\n".join(fm) + "\n\n" + "\n".join(body)


# ---------- Base ----------
def _base_file(prefix: str) -> str:
    folder = f"{prefix}{PAPERS_DIR}"
    cols = ["file.name", "year", "relevance", "origin", "corpus_cites", "cited_by_count", "venue", "seed"]
    order = "\n".join(f"      - {c}" for c in cols)
    sort = "    sort:\n      - property: relevance\n        direction: DESC\n      - property: corpus_cites\n        direction: DESC"

    def view(name: str, filt: str | None = None, extra_cols: tuple[str, ...] = ()) -> str:
        v = ["  - type: table", f"    name: {_yaml_str(name)}"]
        if filt:
            v.append(f"    filters: {filt}")
        v.append("    order:")
        v.append(order + "".join(f"\n      - {c}" for c in extra_cols))
        v.append(sort)
        return "\n".join(v)

    return "\n".join([
        "filters:",
        "  and:",
        "    - " + _yaml_sq(f"file.inFolder({json.dumps(folder, ensure_ascii=False)})"),
        "    - " + _yaml_sq('file.ext == "md"'),
        "properties:",
        "  relevance:\n    displayName: 相关度",
        "  origin:\n    displayName: 来源",
        "  corpus_cites:\n    displayName: 库内被引",
        "  cited_by_count:\n    displayName: 总被引",
        "  year:\n    displayName: 年份",
        "  venue:\n    displayName: 期刊/会议",
        "  seed:\n    displayName: 种子",
        "  relevance_reason:\n    displayName: 相关性理由",
        "views:",
        view("全部文献"),
        view("核心（相关度 ≥ 8）", _yaml_sq("relevance >= 8"), ("relevance_reason",)),
        view("共被引补缺", _yaml_sq('origin == "cocited"'), ("relevance_reason",)),
        view("仅凭标题评分", _yaml_sq('relevance_flag == "no_abstract"'), ("relevance_reason",)),
        view("已撤稿", _yaml_sq("retracted == true")),
    ]) + "\n"


# ---------- Canvas ----------
def _cid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def year_rows(corpus: Corpus, sweeps: int = 6) -> list[tuple[int | None, list[str]]]:
    """One row per year (oldest first); within a row, barycenter sweeps over cross-year neighbours reduce crossings."""
    rows: dict[int | None, list[Paper]] = defaultdict(list)
    for p in corpus.papers:
        rows[p.year].append(p)
    years = sorted(rows, key=lambda y: y if y is not None else 9999)
    nbrs: dict[str, set[str]] = defaultdict(set)
    for e in corpus.edges:
        nbrs[e.source].add(e.target)
        nbrs[e.target].add(e.source)
    year_of = {p.id: p.year for p in corpus.papers}
    order: dict[int | None, list[str]] = {}
    xi: dict[str, float] = {}

    def place(y):
        row = order[y]
        for i, pid in enumerate(row):
            xi[pid] = i - (len(row) - 1) / 2

    for y in years:
        ranked = sorted(rows[y], key=lambda p: (-(p.relevance.score if p.relevance else 0), -(p.cited_by_count or 0)))
        order[y] = [p.id for p in ranked]
        place(y)
    for sweep in range(sweeps):
        for y in (reversed(years) if sweep % 2 else years):
            def bc(pid: str) -> float:
                nb = [xi[m] for m in nbrs[pid] if m in xi and year_of.get(m) != y]
                return sum(nb) / len(nb) if nb else xi[pid]
            order[y].sort(key=bc)
            place(y)
    return [(y, order[y]) for y in years]


def _canvas(corpus: Corpus, names: dict[str, str], indeg: Counter, prefix: str) -> dict:
    by_id = {p.id: p for p in corpus.papers}
    groups, cards = [], []
    y_cursor = 0
    rows = year_rows(corpus)
    max_line = min(PER_LINE, max((len(r) for _, r in rows), default=1))
    full_w = max_line * NODE_W + (max_line - 1) * H_GAP
    for year, row in rows:
        lines = [row[i:i + PER_LINE] for i in range(0, len(row), PER_LINE)]
        top = y_cursor
        y = top + GROUP_PAD
        for line in lines:
            line_w = len(line) * NODE_W + (len(line) - 1) * H_GAP
            x = (full_w - line_w) // 2
            for pid in line:
                cards.append(_card(by_id[pid], names[pid], indeg[pid], prefix, x, y))
                x += NODE_W + H_GAP
            y += NODE_H + V_GAP
        height = y - V_GAP + GROUP_PAD - top
        groups.append({"id": _cid("year", str(year)), "type": "group", "x": -GROUP_PAD, "y": top,
                       "width": full_w + 2 * GROUP_PAD, "height": height,
                       "label": str(year) if year is not None else "年份未知"})
        y_cursor = top + height + GROUP_GAP
    year_of = {p.id: p.year for p in corpus.papers}
    edges = []
    for e in corpus.edges:
        if e.source not in by_id or e.target not in by_id:
            continue
        ed = {"id": _cid("edge", e.source, e.target), "fromNode": _cid("paper", e.source),
              "toNode": _cid("paper", e.target), "toEnd": "arrow"}
        if year_of.get(e.source) != year_of.get(e.target):
            ed.update(fromSide="top", toSide="bottom")  # cited (older) rows sit above citing rows
        if e.relation and e.relation.label != "background":
            ed["label"] = RELATION_NAMES[e.relation.label]
            ed["color"] = RELATION_COLORS[e.relation.label]
        edges.append(ed)
    # Groups first so they render beneath the cards
    return {"nodes": groups + cards, "edges": edges}


def _card(p: Paper, name: str, corpus_cites: int, prefix: str, x: int, y: int) -> dict:
    star = " ★" if p.is_seed else ""
    warn = " ⚠️已撤稿" if p.retracted else ""
    title = p.title if len(p.title) <= 110 else p.title[:107] + "…"
    stats = [f"相关度 {p.relevance.score:g}" if p.relevance else None,
             f"被引 {p.cited_by_count}" if p.cited_by_count is not None else None, f"库内 {corpus_cites}"]
    text = (f"**[[{prefix}{PAPERS_DIR}/{name}|{short_label(p)}]]**{star}{warn}\n{title}\n\n"
            + " · ".join(s for s in stats if s))
    node = {"id": _cid("paper", p.id), "type": "text", "x": x, "y": y, "width": NODE_W, "height": NODE_H, "text": text}
    color = RETRACTED_COLOR if p.retracted else ORIGIN_COLORS.get(p.origin)
    if color:
        node["color"] = color
    return node


# ---------- overview ----------
def _prisma_mermaid(pr: Prisma) -> list[str]:
    ident = " · ".join(f"{ORIGIN_NAMES.get(k, k)} {n}" for k, n in pr.identified.items())
    excl = pr.excluded_low_relevance + pr.excluded_retracted + pr.excluded_over_cap
    q = lambda s: s.replace('"', "'")  # noqa: E731 - mermaid labels are double-quoted
    lines = ["```mermaid", "flowchart TD",
             f'  A["识别（去重后）{sum(pr.identified.values())}<br>{q(ident)}"] --> B["LLM 筛选 {pr.screened}"]',
             f'  A --> N["BM25 预筛未送审 {pr.not_screened}"]',
             f'  B --> X["排除 {excl}<br>相关度不足 {pr.excluded_low_relevance} · 已撤稿 {pr.excluded_retracted}'
             f' · 超出规模上限 {pr.excluded_over_cap}"]',
             f'  B --> I["纳入 {pr.included}' + (f'<br>含 Agent 新增 {pr.agent_added}' if pr.agent_added else "") + '"]',
             "```"]
    if pr.hops:
        lines += [""] + [f"- 第 {h.hop} 跳：新增 {h.candidates}，送筛 {h.screened}，相关 {h.relevant}" for h in pr.hops]
    if pr.stop_reason:
        lines.append(f"- 滚雪球提前停止：{pr.stop_reason}")
    return lines


def _overview(corpus: Corpus, indeg: Counter, link, prefix: str) -> str:
    m, st = corpus.meta, corpus.stats
    it = m.intent
    lines = ["---", "scibooster: true", "tags:", "  - scibooster/overview", "---", "",
             f"# {m.prompt or '文献图谱'}", ""]
    lines += [f"{st.get('n_papers', len(corpus.papers))} 篇文献（种子 {st.get('n_seeds', 0)}）· "
              f"{st.get('n_edges', len(corpus.edges))} 条库内引用 · 年份 {st.get('year_span')}", "",
              f"- 引用图谱（按年代分层，旧在上）：[[{prefix}{CANVAS}]]",
              f"- 文献表：[[{prefix}{BASE}]]（需要 Obsidian 1.9 及以上）", ""]
    if it:
        lines += ["## 研究意图", "", it.topic, ""] + [f"- {q}" for q in it.research_questions] + [""]
    if m.queries:
        lines += ["## 检索式", ""] + [f"- `{q}`" for q in m.queries] + [""]
    if m.summary:
        lines += ["## Agent 总结", "", m.summary, ""]
    if m.prisma:
        lines += ["## 筛选流程（PRISMA）", ""] + _prisma_mermaid(m.prisma) + [""]
    top = sorted(corpus.papers, key=lambda p: -indeg[p.id])[:10]
    if top and indeg[top[0].id]:
        lines += ["## 库内被引最多", ""]
        lines += [f"{i}. {link(p.id)} {p.title} — 库内被引 {indeg[p.id]}" for i, p in enumerate(top, 1) if indeg[p.id]]
        lines.append("")
    lines += ["## 文献表", "", f"![[{prefix}{BASE}#全部文献]]", ""]
    u = m.usage
    lines += [f"*生成于 {m.created_at} · DeepSeek {u.deepseek_calls} 次调用 / "
              f"{u.deepseek_prompt_tokens + u.deepseek_completion_tokens} tokens · OpenAlex {u.openalex_requests} 次请求*",
              "", NOTES_MARKER]
    return "\n".join(lines)
