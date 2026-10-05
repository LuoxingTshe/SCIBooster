import json

import yaml

from scibooster.models import EdgeRelation, Paper, Prisma
from scibooster.obsidian import BASE, CANVAS, NOTES_MARKER, OVERVIEW, export_vault, note_names
from scibooster.store import CorpusStore


def _corpus(small_corpus):
    c = CorpusStore(small_corpus).finalize()
    c.edges[0].relation = EdgeRelation(label="extends", rationale="builds on it")
    c.meta.prompt = "GNN 药物发现"
    c.meta.prisma = Prisma(identified={"seed": 1, "openalex_search": 6}, screened=6, included=7)
    return c


def _frontmatter(path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    return yaml.safe_load(text.split("---\n", 2)[1])


def test_vault_layout_and_properties(small_corpus, tmp_path):
    c = _corpus(small_corpus)
    rep = export_vault(c, tmp_path / "SCIBooster" / "run1", vault_root=tmp_path)
    out = tmp_path / "SCIBooster" / "run1"
    notes = sorted((out / "papers").glob("*.md"))
    assert rep.notes_written == len(notes) == 7 and (out / OVERVIEW).exists()

    e = c.edges[0]
    src = next(p for p in c.papers if p.id == e.source)
    fm = _frontmatter(out / "papers" / f"{note_names(c.papers)[src.id]}.md")
    assert fm["paper_id"] == src.id and fm["scibooster"] is True and fm["year"] == src.year
    assert "scibooster/paper" in fm["tags"]
    # Links carry the vault-relative path, so runs sharing one vault never collide
    assert all(link.startswith("[[SCIBooster/run1/papers/") for link in fm["cites"])
    assert len(fm["extends"]) == 1 and fm["extends"][0] in fm["cites"]

    base = yaml.safe_load((out / BASE).read_text(encoding="utf-8"))
    assert base["filters"]["and"][0] == 'file.inFolder("SCIBooster/run1/papers")'
    assert [v["name"] for v in base["views"]][0] == "全部文献"
    assert all(v["type"] == "table" and "file.name" in v["order"] for v in base["views"])

    overview = (out / OVERVIEW).read_text(encoding="utf-8")
    assert "```mermaid" in overview and "[[SCIBooster/run1/引用图谱.canvas]]" in overview


def test_canvas_is_valid_year_layered_dag(small_corpus, tmp_path):
    c = _corpus(small_corpus)
    export_vault(c, tmp_path)
    canvas = json.loads((tmp_path / CANVAS).read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in canvas["nodes"]}
    assert len(nodes) == len(canvas["nodes"])  # unique ids
    for n in canvas["nodes"]:
        assert {"id", "type", "x", "y", "width", "height"} <= n.keys()
        assert all(isinstance(n[k], int) for k in ("x", "y", "width", "height"))
    cards = [n for n in canvas["nodes"] if n["type"] == "text"]
    groups = [n for n in canvas["nodes"] if n["type"] == "group"]
    assert len(cards) == 7 and {g["label"] for g in groups} == {str(p.year) for p in c.papers}
    assert canvas["nodes"].index(groups[-1]) < canvas["nodes"].index(cards[0])  # groups render beneath cards
    assert len(canvas["edges"]) == len(c.edges)
    for ed in canvas["edges"]:
        src, dst = nodes[ed["fromNode"]], nodes[ed["toNode"]]
        assert src["y"] >= dst["y"]  # citing paper sits on or below the (older) cited one
    labeled = [ed for ed in canvas["edges"] if "label" in ed]
    assert len(labeled) == 1 and labeled[0]["label"] == "扩展/改进"
    # Each card sits inside its year's group
    year_group = {g["label"]: g for g in groups}
    for card in cards:
        pid = next(p for p in c.papers if f"|{p.authors[0].split()[-1]} {p.year}]]" in card["text"] and p.title[:20] in card["text"])
        g = year_group[str(pid.year)]
        assert g["y"] <= card["y"] and card["y"] + card["height"] <= g["y"] + g["height"]


def test_reexport_keeps_user_notes_and_cleans_stale(small_corpus, tmp_path):
    c = _corpus(small_corpus)
    export_vault(c, tmp_path)
    names = note_names(c.papers)
    keep_id, drop_id = c.papers[1].id, c.papers[2].id
    kept = tmp_path / "papers" / f"{names[keep_id]}.md"
    kept.write_text(kept.read_text(encoding="utf-8") + "我的批注：方法很重要\n", encoding="utf-8")
    overview = tmp_path / OVERVIEW
    overview.write_text(overview.read_text(encoding="utf-8") + "综述提纲\n", encoding="utf-8")
    (tmp_path / "papers" / "随手记.md").write_text("not generated", encoding="utf-8")

    store = CorpusStore(c.model_copy(deep=True))
    store.remove(keep_id)
    store.remove(drop_id)
    rep = export_vault(store.finalize(), tmp_path)
    assert rep.stale_kept == [kept.name] and kept.exists() and "方法很重要" in kept.read_text(encoding="utf-8")
    assert rep.stale_removed == [f"{names[drop_id]}.md"]
    assert (tmp_path / "papers" / "随手记.md").exists()  # files we didn't generate are never touched
    assert "综述提纲" in overview.read_text(encoding="utf-8")

    # Re-adding the paper regenerates the note above the marker and keeps the user's text below it
    rep = export_vault(c, tmp_path)
    text = kept.read_text(encoding="utf-8")
    assert rep.notes_kept_user_text == 1 and text.count(NOTES_MARKER) == 1 and text.endswith("我的批注：方法很重要\n")


def test_note_names_are_safe_and_unique():
    ps = [Paper(id="W1", title='A/B: "test"? [x]#1', authors=["Ann Lee"], year=2020),
          Paper(id="W2", title='A/B: "test"? [x]#1', authors=["Ann Lee"], year=2020),
          Paper(id="W3", title="", authors=[], year=None)]
    names = note_names(ps)
    assert names["W1"] == "Lee 2020 - A B test x 1"
    assert names["W2"] == "Lee 2020 - A B test x 1 (W2)" and names["W3"] == "Anon n.d. - W3"
    assert not any(ch in n for n in names.values() for ch in '\\/:*?"<>|#^[]')
