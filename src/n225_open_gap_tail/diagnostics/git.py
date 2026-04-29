from __future__ import annotations

from n225_open_gap_tail.config import git as _git


def _git_commit() -> str:
    return _git._git_commit()


def _git_dirty() -> bool:
    return _git._git_dirty()
