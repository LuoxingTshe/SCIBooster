import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import FakeLLM, FakeOA
from scibooster import cli
from scibooster.config import Settings
from scibooster.models import Corpus
from scibooster.runtime import MARKER, RetrievalRun
from scibooster.sources.cache import Cache


def settings(tmp_path):
    return Settings(_env_file=None, scib_corpora_dir=tmp_path / 'runs', scib_cache_dir=tmp_path / 'cache',
                    scib_keep_history=False, scib_keep_cache=False)


def corpus(directory):
    path = directory / 'corpus.json'
    path.write_text(Corpus().model_dump_json())
    return path


def finished(s, name, **options):
    folder = s.scib_corpora_dir / name
    with RetrievalRun(s, folder, kind='build', **options) as run:
        run.complete([corpus(folder)])
    return folder


def test_success_prunes_only_owned_completed_results_and_vacuums_cache(tmp_path):
    s = settings(tmp_path)
    old = finished(s, 'old')
    unknown = s.scib_corpora_dir / 'manual-notes'
    unknown.mkdir(); (unknown / 'note.txt').write_text('Keep me')
    outside = tmp_path / 'outside'; outside.mkdir(); corpus(outside)
    (s.scib_corpora_dir / 'linked').symlink_to(outside, target_is_directory=True)
    cache = Cache(s.scib_cache_dir / 'http.sqlite'); cache.set('key', 'x' * 1000000); cache.close()
    size = (s.scib_cache_dir / 'http.sqlite').stat().st_size
    new = finished(s, 'new')
    assert not old.exists() and new.exists() and unknown.exists() and outside.exists()
    cache = Cache(s.scib_cache_dir / 'http.sqlite')
    assert cache.get('key') is None
    assert cache.path.stat().st_size < size
    cache.close()
    report = json.loads((new / 'cleanup.json').read_text())
    assert report['removed_runs'] == ['old'] and not report['errors']


@pytest.mark.parametrize('error', [RuntimeError('export failed'), KeyboardInterrupt()])
def test_failure_and_interrupt_preserve_previous_result_and_cache(tmp_path, error):
    s = settings(tmp_path); old = finished(s, 'old')
    target = s.scib_corpora_dir / 'failed'
    with pytest.raises(type(error)):
        with RetrievalRun(s, target, kind='build') as run:
            cache = run.cache(Cache(s.scib_cache_dir / 'http.sqlite'))
            cache.set('key', 'retained')
            corpus(target)  # even a saved corpus must not trigger cleanup before export succeeds
            raise error
    assert old.exists()
    assert json.loads((target / MARKER).read_text())['status'] in {'incomplete', 'interrupted'}
    cache = Cache(s.scib_cache_dir / 'http.sqlite'); assert cache.get('key') == 'retained'; cache.close()
    finished(s, 'next')
    assert target.exists()  # keep failure diagnostics


def test_validation_and_keep_options(tmp_path):
    s = settings(tmp_path); old = finished(s, 'old')
    folder = s.scib_corpora_dir / 'kept'
    with RetrievalRun(s, folder, kind='build', keep_history=True, keep_cache=True) as run:
        cache = run.cache(Cache(folder / 'http.sqlite')); cache.set('k', 'v')
        run.complete([corpus(folder)])
    assert old.exists()
    cache = Cache(folder / 'http.sqlite'); assert cache.get('k') == 'v'; cache.close()
    bad = s.scib_corpora_dir / 'bad'
    with pytest.raises(ValueError):
        with RetrievalRun(s, bad, kind='build') as run:
            (bad / 'corpus.json').write_text('not json')
            run.complete([bad / 'corpus.json'])
    assert old.exists() and folder.exists()


def test_custom_output_does_not_prune_managed_root_and_lock_blocks_concurrent_runs(tmp_path):
    s = settings(tmp_path); old = finished(s, 'old')
    with RetrievalRun(s, tmp_path / 'custom', kind='build') as run:
        with pytest.raises(RuntimeError, match='Another retrieval'):
            with RetrievalRun(s, s.scib_corpora_dir / 'concurrent', kind='build'):
                pytest.fail('must not enter')
        run.complete([corpus(tmp_path / 'custom')])
    assert old.exists()
    with pytest.raises(ValueError, match='empty directory'):
        with RetrievalRun(s, old, kind='build'):
            pytest.fail('must not overwrite a completed result')
    assert json.loads((old / MARKER).read_text())['status'] == 'completed'


def fake_clients(monkeypatch, s):
    monkeypatch.setattr(cli, 'get_settings', lambda: s)
    def clients(tracer, source, run=None):
        cache = Cache(s.scib_cache_dir / 'http.sqlite')
        cache.set('sentinel', 'cached')
        if run:
            run.cache(cache)
        return FakeLLM(), FakeOA(), None
    monkeypatch.setattr(cli, '_clients', clients)


def test_build_cli_cleanup_waits_for_obsidian_and_keeps_complete_output(tmp_path, monkeypatch):
    s = settings(tmp_path); old = finished(s, 'old'); fake_clients(monkeypatch, s)
    runner = CliRunner(); out = s.scib_corpora_dir / 'new' / 'corpus.json'
    def export(*args, **kwargs):
        assert old.exists()
        (out.parent / 'obsidian').mkdir()
        (out.parent / 'obsidian' / '总览.md').write_text('complete export')
    monkeypatch.setattr(cli, '_write_obsidian', export)
    result = runner.invoke(cli.app, ['build', 'graph', '--source', 'openalex', '--out', str(out)])
    assert result.exit_code == 0, result.output
    assert not old.exists() and (out.parent / 'obsidian' / '总览.md').exists()
    cache = Cache(s.scib_cache_dir / 'http.sqlite'); assert cache.get('sentinel') is None; cache.close()
    def failing_export(*args, **kwargs):
        raise OSError('export failed')
    monkeypatch.setattr(cli, '_write_obsidian', failing_export)
    result = runner.invoke(cli.app, ['build', 'graph', '--source', 'openalex', '--out', str(s.scib_corpora_dir / 'bad' / 'corpus.json')])
    assert result.exit_code != 0 and out.exists()


def test_agent_continuation_uses_new_directory_and_unfinished_agent_does_not_prune(tmp_path, monkeypatch):
    from scibooster.agent import loop
    s = settings(tmp_path); old = finished(s, 'old'); fake_clients(monkeypatch, s)
    before = (old / 'corpus.json').read_bytes()
    runner = CliRunner()
    monkeypatch.setattr(loop, 'run_agent', lambda *args, **kwargs: None)
    result = runner.invoke(cli.app, ['agent', 'graph', '--corpus', str(old / 'corpus.json'), '--no-obsidian'])
    assert result.exit_code == 0, result.output
    assert (old / 'corpus.json').read_bytes() == before
    def finish(ctx, *args, **kwargs):
        ctx.finished = True
    monkeypatch.setattr(loop, 'run_agent', finish)
    result = runner.invoke(cli.app, ['agent', 'graph', '--corpus', str(old / 'corpus.json'), '--no-obsidian'])
    assert result.exit_code == 0, result.output
    assert not old.exists()
    complete = [p for p in s.scib_corpora_dir.glob('*/'+MARKER) if json.loads(p.read_text())['status']=='completed']
    assert len(complete) == 1


def test_invalid_or_linked_ownership_marker_is_never_pruned(tmp_path):
    s = settings(tmp_path)
    root = s.scib_corpora_dir
    root.mkdir()
    invalid = root / 'invalid'; invalid.mkdir()
    (invalid / MARKER).write_text('[]')
    linked = root / 'linked-marker'; linked.mkdir()
    outside_marker = tmp_path / 'outside-marker.json'
    outside_marker.write_text(json.dumps({'owner': 'scibooster', 'status': 'completed'}))
    (linked / MARKER).symlink_to(outside_marker)
    finished(s, 'new')
    assert invalid.exists() and linked.exists()


def script_clients(monkeypatch, s):
    from scibooster import config
    from scibooster.llm import deepseek
    from scibooster.sources import openalex, wos
    monkeypatch.setattr(config, 'get_settings', lambda: s.model_copy(update={'deepseek_api_key': 'fake', 'wos_api_key': 'fake'}))
    monkeypatch.setattr(deepseek, 'DeepSeek', lambda *args: FakeLLM())
    def oa(settings, cache, tracer):
        cache.set('sentinel', 'cached response')
        return FakeOA()
    monkeypatch.setattr(openalex, 'OpenAlexClient', oa)
    monkeypatch.setattr(wos, 'WosClient', lambda *args: None)


@pytest.mark.parametrize('fail', [False, True])
def test_two_branch_script_cleans_only_after_successful_report(tmp_path, monkeypatch, fail):
    from scripts import timeline_retrieval as script
    from scibooster.store import CorpusStore
    s = settings(tmp_path); old = finished(s, 'old'); script_clients(monkeypatch, s)
    baselines = script.load_baseline()
    config, params = script.load_case()
    def build(params, llm, oa, wos, tracer, out, **kwargs):
        branch = out.parent.name
        if fail and branch == 'formal_methods':
            raise RuntimeError('second branch failed')
        store = CorpusStore(baselines[branch].model_copy(deep=True))
        store.save(out)
        return store
    monkeypatch.setattr(script, 'build_corpus', build)
    output = s.scib_corpora_dir / 'branches'
    if fail:
        with pytest.raises(RuntimeError, match='second branch'):
            script.run_live(output, config, params)
        assert old.exists()
        assert json.loads((output / 'run.json').read_text())['status'] == 'failed'
    else:
        assert script.run_live(output, config, params) == 0
        assert not old.exists() and (output / 'comparison.md').exists()
        assert json.loads((output / 'run.json').read_text())['status'] == 'passed'
    cache = Cache(output / 'history' / 'http.sqlite')
    assert (cache.get('sentinel') is not None) == fail
    cache.close()


def test_variance_reanalysis_survives_source_result_pruning(tmp_path, monkeypatch):
    from scripts import timeline_retrieval as retrieval, timeline_variance as variance
    from scibooster.store import CorpusStore
    s = settings(tmp_path); script_clients(monkeypatch, s)
    baselines = retrieval.load_baseline()
    source = s.scib_corpora_dir / 'source'
    with RetrievalRun(s, source, kind='timeline-study', keep_cache=True) as run:
        paths = []
        for branch, c in baselines.items():
            folder = source / branch; folder.mkdir()
            paths.append(CorpusStore(c.model_copy(deep=True)).save(folder / 'corpus.json'))
            run.cache(Cache(folder / 'http.sqlite')).set('sentinel', 'cached')
        run.complete(paths)
    def build(params, llm, oa, wos, tracer, out, **kwargs):
        store = CorpusStore(baselines[out.parent.name].model_copy(deep=True))
        store.save(out)
        return store
    monkeypatch.setattr(variance.build, 'build_corpus', build)
    output = s.scib_corpora_dir / 'variance'
    assert variance.run(output, source, 1) == 0
    assert not source.exists()
    assert variance.analyze(output)['replicates'] == 1
    for branch in retrieval.BRANCHES:
        assert (output / 'inputs' / branch / 'corpus.json').exists()
        cache = Cache(output / 'rep1' / branch / 'http.sqlite')
        assert cache.get('sentinel') is None
        cache.close()
