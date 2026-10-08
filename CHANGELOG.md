# Release notes

## beta1.0 — 2026-10-08

First official Beta release. Git tag: `beta1.0`; Python package version: `1.0.0b1`.

- Retrieve literature through WoS Starter and OpenAlex with DeepSeek intent parsing and relevance screening, citation expansion, co-citation gap filling and an optional tool-calling Agent.
- Export a citation-linked corpus, Obsidian notes and Canvas, BibTeX, RIS and CSV; evaluate recall against fixed literature packages.
- Merge duplicate literature versions conservatively, prefer published records, preserve original versions and citation provenance, and report uncertain matches for review. Existing corpora can be deduplicated offline into a new directory.
- Store runtime caches and results separately under `artifacts/`. Test cases retain literature inputs, gold sets, baselines and test pipelines.
- After successful retrieval and output generation, retain the latest complete result and clear cached responses. Failed, interrupted and incomplete runs preserve earlier results; `--keep-history` and `--keep-cache` support repeat experiments.
- Continue Agent sessions in a new directory and snapshot source corpora for variance experiments so offline analysis survives result cleanup.
- Display the release with `scibooster --version`.

Validation: 96 offline Python tests and 8 citation-layout tests pass. No paid API calls are needed for these checks. Actual retrieval requires configured API credentials; see the README for setup and current retrieval limitations.
