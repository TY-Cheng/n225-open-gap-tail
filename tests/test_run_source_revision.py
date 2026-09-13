from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from n225_open_gap_tail.config.git import _saved_source_matches_commit
from n225_open_gap_tail.config.runtime import PIPELINE_CONFIG, PipelineRunError
from n225_open_gap_tail.metrics.information import _assert_run_config_compatible


def test_committed_snapshot_allows_guard_without_rewriting_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL)

    git("init")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    source = tmp_path / "src"
    source.mkdir()
    model = source / "model.py"
    model.write_text("value = 1\n")
    git("add", "src")
    git("commit", "-m", "original")
    old = git("rev-parse", "HEAD").decode().strip()
    model.write_text("value = 2\n")
    run = tmp_path / "run"
    (run / "source").mkdir(parents=True)
    patch = run / "source/working-tree.patch"
    patch.write_bytes(git("diff", "HEAD", "--", "src", "pyproject.toml"))
    manifest = run / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "git_commit": old,
                "git_dirty": True,
                "config_hash": PIPELINE_CONFIG.config_hash(),
            }
        )
    )
    original = manifest.read_bytes()
    git("add", "src")
    git("commit", "-m", "commit saved work")
    current = git("rev-parse", "HEAD").decode().strip()
    assert _saved_source_matches_commit(run, old, current)
    _assert_run_config_compatible(run)
    assert manifest.read_bytes() == original

    (run / "source/src").mkdir()
    assert not _saved_source_matches_commit(run, old, current)
    (run / "source/src").rmdir()
    assert not _saved_source_matches_commit(run, "missing-revision", current)
    saved = patch.read_bytes()
    patch.write_bytes(saved.replace(b"value = 2", b"value = 3"))
    with pytest.raises(PipelineRunError, match="source revision"):
        _assert_run_config_compatible(run, force=True)
    patch.unlink()
    assert not _saved_source_matches_commit(run, old, current)
    patch.write_bytes(saved)
    (run / "forecasts").mkdir()
    (run / "forecasts/placeholder").touch()
    manifest.write_text(json.dumps({"git_commit": old, "config_hash": "different"}))
    with pytest.raises(PipelineRunError, match="config is locked"):
        _assert_run_config_compatible(run)
    manifest.write_bytes(original)

    (tmp_path / "uv.lock").write_text("changed dependency lock\n")
    git("add", "uv.lock")
    git("commit", "-m", "dependency change")
    assert not _saved_source_matches_commit(run, old, git("rev-parse", "HEAD").decode().strip())
    model.write_text("value = 3\n")
    git("add", "src")
    git("commit", "-m", "different model")
    with pytest.raises(PipelineRunError, match="source revision"):
        _assert_run_config_compatible(run, force=True)
    assert manifest.read_bytes() == original
