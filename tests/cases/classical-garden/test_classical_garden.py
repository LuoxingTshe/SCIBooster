import json
import sys

import pytest

from scripts.real_search import FIXTURE, evaluate, load_case, main
from scibooster.models import Corpus, Edge, Paper, Relevance
from scibooster.pipeline.seeds import classify, read_seed_file


def test_fixture_inputs_are_cli_ready():
    seeds = read_seed_file(FIXTURE / "core_literature.txt")
    intent = (FIXTURE / "research_intent.txt").read_text(encoding="utf-8")
    assert len(seeds) == 3 and len(set(seeds)) == 3
    assert all(classify(seed)[0] == "doi" for seed in seeds)
    for phrase in ("中国古典园林", "三维点云", "纳入范围", "排除范围"):
        assert phrase in intent


def sample_corpus(gold):
    papers = [Paper(id=f"W{i}", doi=g["doi"], title=g["title"], year=2024,
                    is_seed=g["role"] == "seed", origin="seed" if g["role"] == "seed" else "wos_search",
                    relevance=Relevance(score=10 if g["role"] == "seed" else 7))
              for i, g in enumerate(gold) if g["role"] != "review"]
    return Corpus(papers=papers, edges=[Edge(source=papers[0].id, target=papers[1].id)])


def test_evaluator_reports_distinct_nonseed_recall_and_roles():
    config, _, gold = load_case()
    corpus = sample_corpus(gold)
    r = evaluate(corpus, config, gold)
    assert r["passed"] and (r["gold_hits"], r["nonseed_hits"], r["nonseed_total"]) == (9, 6, 7)
    assert r["by_role"]["review"] == {"hits": 0, "total": 1}
    assert r["score_histogram"] == {"7.0": 6}  # seed scores are not independent quality evidence
    corpus.papers.append(corpus.papers[-1].model_copy(deep=True))
    r = evaluate(corpus, config, gold)
    assert r["gold_hits"] == 9 and r["nonseed_hits"] == 6
    assert "duplicate_ids_or_dois" in r["errors"]


@pytest.mark.parametrize("change,error", [
    ({"year": 2026}, "out_of_year"),
    ({"year": None}, "unknown_year"),
    ({"is_seed": True}, "seed_resolution_or_seed_leakage"),
    ({"doi": "10.1234/different-work"}, "nonseed_recall_below_baseline"),
])
def test_quality_gate_rejects_years_leaked_seeds_and_missing_targets(change, error):
    config, _, gold = load_case()
    corpus = sample_corpus(gold)
    p = next(p for p in corpus.papers if not p.is_seed)
    for key, value in change.items():
        setattr(p, key, value)
    r = evaluate(corpus, config, gold)
    assert not r["passed"] and error in r["errors"]


def test_plan_and_evaluate_are_offline_and_refuse_overwrite(tmp_path, monkeypatch, capsys):
    from scibooster import config as settings_module

    def no_clients():
        raise AssertionError("offline commands must not load API settings")
    monkeypatch.setattr(settings_module, "get_settings", no_clients)
    monkeypatch.setattr(sys, "argv", ["real_search", "plan"])
    assert main() == 0
    plan = json.loads(capsys.readouterr().out)
    assert len(plan["seeds"]) == 3 and len(plan["queries"]) == 7
    config, _, gold = load_case()
    source = tmp_path / "corpus.json"
    source.write_text(sample_corpus(gold).model_dump_json(), encoding="utf-8")
    out = tmp_path / "audit"
    monkeypatch.setattr(sys, "argv", ["real_search", "evaluate", str(source), "--out", str(out)])
    assert main() == 0
    assert json.loads((out / "benchmark.json").read_text())["passed"]
    assert (out / "benchmark.md").exists()
    with pytest.raises(FileExistsError):
        main()
