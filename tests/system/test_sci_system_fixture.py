from pathlib import Path

from scibooster.pipeline.seeds import classify, read_seed_file


FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "real_search"


def test_classical_garden_system_fixture_is_cli_ready():
    seeds = read_seed_file(FIXTURE_DIR / "core_literature.txt")
    intent = (FIXTURE_DIR / "research_intent.txt").read_text(encoding="utf-8")

    assert len(seeds) == 3
    assert len(set(seeds)) == len(seeds)
    assert all(classify(seed)[0] == "doi" for seed in seeds)
    assert "中国古典园林" in intent
    assert "三维点云" in intent
    assert "纳入范围" in intent
    assert "排除范围" in intent
