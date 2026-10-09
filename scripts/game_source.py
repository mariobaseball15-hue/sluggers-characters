"""The player's clean game (RMBE01, extracted): where the build's helpers read Nintendo's files from.

Default ROOT/extracted/clean. The patcher points it at the player's own copy:

    with game_source.use(path):     # a build: restores the previous root on exit
        charbuild.build(...)
    game_source.set_root(path)      # a script
"""
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "extracted/clean"
_root = DEFAULT


def root():
    """The clean game's folder (sys/main.dol, files/dt_na.dat, ...)."""
    return _root


def set_root(path):
    global _root
    _root = Path(path) if path is not None else DEFAULT


@contextmanager
def use(path):
    prev = _root
    set_root(path)
    try:
        yield _root
    finally:
        set_root(prev)
