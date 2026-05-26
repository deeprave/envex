import argparse
import logging
import sys

import pytest

from envex.scripts import seal
from envex.scripts.lib import log as script_log
from envex.scripts.lib.decr_action import Decrement


def test_decrement_rejects_non_numeric_state(capsys):
    parser = argparse.ArgumentParser(prog="quiet-test")
    parser.add_argument("--quiet", action=Decrement, dest="level", default="bad")

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--quiet"])

    assert exc_info.value.code == 2
    assert "level must be an integer" in capsys.readouterr().err


def test_log_set_level_updates_current_level():
    previous_level = logging.getLogger().level
    try:
        assert script_log.log_get_level(script_log.log_set_level(4)) == 4
        assert script_log.log_get_level() == 4
        assert script_log.log_get_level(script_log.log_set_level(-1)) == 0
        assert script_log.log_get_level() == 0
    finally:
        script_log.log_set_level()
        logging.getLogger().setLevel(previous_level)


def test_seal_exits_nonzero_on_operational_error(monkeypatch, caplog):
    class FakeClient:
        @property
        def seal_status(self):
            raise RuntimeError("status failed")

    monkeypatch.setattr(seal.hvac, "Client", lambda **_kwargs: FakeClient())
    monkeypatch.setattr(
        sys, "argv", ["seal", "--address", "http://vault.local", "--token", "token"]
    )
    caplog.set_level(logging.ERROR)

    with pytest.raises(SystemExit) as exc_info:
        seal.main()

    assert exc_info.value.code == 1
    assert "RuntimeError: status failed" in caplog.text
