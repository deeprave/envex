# -*- coding: utf-8 -*-
from pathlib import Path

__all__ = ("current_working_dir",)


def current_working_dir() -> str | None:
    try:
        return Path.cwd().resolve(strict=True).as_posix()
    except FileNotFoundError:
        return None
