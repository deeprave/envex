import sys

import pytest

from envex.scripts import envsecrets


def test_main_supports_console_script_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["envsecrets", "--help"])

    with pytest.raises(SystemExit) as exc_info:
        envsecrets.main()

    assert exc_info.value.code == 0
    assert "usage: envsecrets" in capsys.readouterr().out


def test_main_parses_argv_and_writes_env_and_secrets(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("PUBLIC=hello\nSECRET=shh\n")
    template = tmp_path / "template.env"
    template.write_text(
        "PUBLIC\n"
        "|SECRET\n"
        "DEFAULT=fallback\n"
        "COMPOSED=${MISSING:-fallback-$PUBLIC}\n"
        "NO_BRACES=$PUBLIC\n"
        "CALLBACK=https://${HOST}/cb\n"
        "PRICE=cost-$5\n"
    )
    output = tmp_path / "docker.env"
    captured = []

    def fake_create_or_update_secrets(secrets, key, cert, verbose):
        captured.append(
            {
                "secrets": secrets,
                "key": key,
                "cert": cert,
                "verbose": verbose,
            }
        )

    monkeypatch.setattr(
        envsecrets, "create_or_update_secrets", fake_create_or_update_secrets
    )

    envsecrets.main(
        (
            "--dotenv",
            str(dotenv),
            "--template",
            str(template),
            "--key",
            "app",
            str(output),
        )
    )

    assert output.read_text().splitlines() == [
        "PUBLIC=hello",
        "DEFAULT=fallback",
        "COMPOSED=fallback-hello",
        "NO_BRACES=hello",
        "CALLBACK=https://${HOST}/cb",
        "PRICE=cost-$5",
    ]
    assert captured == [
        {
            "secrets": {"SECRET": "shh"},
            "key": "app",
            "cert": None,
            "verbose": False,
        }
    ]


def test_main_uses_default_output_path(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("PUBLIC=hello\n")
    template = tmp_path / "template.env"
    template.write_text("PUBLIC\n")

    monkeypatch.chdir(tmp_path)

    envsecrets.main(
        [
            "--dotenv",
            str(dotenv),
            "--template",
            str(template),
        ]
    )

    assert (tmp_path / "docker.env").read_text().splitlines() == ["PUBLIC=hello"]


def test_read_env_uses_absolute_dotenv_when_current_working_dir_is_missing(
    tmp_path, monkeypatch, capsys
):
    dotenv = tmp_path / ".env"
    dotenv.write_text("PUBLIC=hello\n")
    monkeypatch.setattr(envsecrets, "current_working_dir", lambda: None)

    assert envsecrets.read_env(dotenv) == {"PUBLIC": "hello"}
    assert capsys.readouterr().err == ""


def test_read_env_warns_when_default_search_path_is_unavailable(monkeypatch, capsys):
    monkeypatch.setattr(envsecrets, "current_working_dir", lambda: None)

    assert envsecrets.read_env(None) == {}
    assert (
        "WARNING: current working directory is unavailable; "
        "skipping default dotenv search path"
    ) in capsys.readouterr().err
