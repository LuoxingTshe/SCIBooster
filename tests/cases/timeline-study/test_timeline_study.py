import hashlib
import json
import sys

import pytest

from scripts.timeline_retrieval import (BRANCHES, CASE, compare, expected_queries, load_baseline, load_case,
                                        main, read_json)


def test_case_files_match_source_manifest():
    manifest = read_json(CASE / "SOURCE_MANIFEST.json")
    assert manifest["files"]
    for f in manifest["files"]:
        assert hashlib.sha256((CASE / f["case_path"]).read_bytes()).hexdigest() == f["sha256"], f["case_path"]


def test_baseline_reproduces_itself_and_the_79_candidate_list():
    _, params = load_case()
    r = compare(load_baseline(), params)
    assert r["passed"], r["errors"]
    assert r["union"] == {"baseline": 79, "reproduced": 79, "shared": 79, "baseline_recall": 1.0}
    assert {k: v["baseline_papers"] for k, v in r["branches"].items()} == {"history": 21, "formal_methods": 58}
    ds = r["direct_support"]
    assert (ds["harness_total"], ds["harness_hits"], ds["nonseed_total"], ds["nonseed_hits"]) == (20, 20, 11, 11)


def test_baseline_ran_the_frozen_queries():
    _, params = load_case()
    for name, corpus in load_baseline().items():
        assert corpus.meta.queries == expected_queries(params[name])
        assert all(q.endswith("AND PY=(1900-2026)") for q in corpus.meta.queries)


@pytest.mark.parametrize("mutate,error", [
    (lambda c: setattr(c.papers[0], "is_seed", False), "history: seed_resolution"),
    (lambda c: c.meta.queries.pop(), "history: executed_queries_differ_from_fixed_case"),
    (lambda c: c.papers.append(c.papers[-1].model_copy(deep=True)), "history: duplicate_keys"),
])
def test_compare_flags_structural_drift(mutate, error):
    _, params = load_case()
    runs = load_baseline()
    assert runs["history"].papers[0].is_seed
    mutate(runs["history"])
    r = compare(runs, params)
    assert not r["passed"] and error in r["errors"]


def test_dropped_paper_lowers_overlap_but_is_not_a_structural_error():
    _, params = load_case()
    runs = load_baseline()
    dropped = next(p for p in runs["formal_methods"].papers if not p.is_seed)
    runs["formal_methods"].papers.remove(dropped)
    r = compare(runs, params)
    b = r["branches"]["formal_methods"]
    assert r["passed"] and b["shared"] == 57 and len(b["missing"]) == 1


def test_plan_and_compare_are_offline(tmp_path, monkeypatch, capsys):
    from scibooster import config as settings_module

    def no_clients():
        raise AssertionError("offline commands must not load API settings")
    monkeypatch.setattr(settings_module, "get_settings", no_clients)
    monkeypatch.setattr(sys, "argv", ["timeline_retrieval", "plan"])
    assert main() == 0
    plan = json.loads(capsys.readouterr().out)
    assert set(plan) == set(BRANCHES) and all(len(b["queries"]) == 3 for b in plan.values())
    for name, corpus in load_baseline().items():
        (tmp_path / name).mkdir()
        (tmp_path / name / "corpus.json").write_text(corpus.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["timeline_retrieval", "compare", str(tmp_path)])
    assert main() == 0
    assert json.loads((tmp_path / "comparison.json").read_text())["union"]["shared"] == 79
