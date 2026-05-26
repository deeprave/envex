import logging

import pytest

from envex.scripts import envcrypt


PASSWORD = "Strong#Pass123"


def test_main_supports_console_script_help(caplog):
    caplog.set_level(logging.INFO)

    with pytest.raises(SystemExit) as exc_info:
        envcrypt.main(["--help"])

    assert exc_info.value.code == 0
    assert "usage:" in caplog.text


def test_main_requires_operation(tmp_path, caplog):
    input_file = tmp_path / ".env"
    input_file.write_text("VALUE=ok\n")
    caplog.set_level(logging.ERROR)

    with pytest.raises(SystemExit) as exc_info:
        envcrypt.main(["--password", PASSWORD, str(input_file)])

    assert exc_info.value.code == 3
    assert "operation to perform" in caplog.text


def test_main_rejects_legacy_with_encrypt(tmp_path, caplog):
    input_file = tmp_path / ".env"
    input_file.write_text("VALUE=ok\n")
    output_file = tmp_path / ".env.enc"
    caplog.set_level(logging.ERROR)

    with pytest.raises(SystemExit) as exc_info:
        envcrypt.main(
            [
                "--encrypt",
                "--legacy",
                "--password",
                PASSWORD,
                str(input_file),
                str(output_file),
            ]
        )

    assert exc_info.value.code == 3
    assert "--legacy can only be used with --decrypt" in caplog.text


def test_main_encrypts_and_decrypts_files(tmp_path):
    input_file = tmp_path / ".env"
    encrypted_file = tmp_path / ".env.enc"
    decrypted_file = tmp_path / ".env.out"
    input_file.write_text("VALUE=ok\n")

    envcrypt.main(
        ["--encrypt", "--password", PASSWORD, str(input_file), str(encrypted_file)]
    )
    envcrypt.main(
        ["--decrypt", "--password", PASSWORD, str(encrypted_file), str(decrypted_file)]
    )

    assert encrypted_file.read_bytes() != input_file.read_bytes()
    assert decrypted_file.read_text() == "VALUE=ok\n"


def test_main_removes_input_after_successful_conversion(tmp_path):
    input_file = tmp_path / ".env"
    encrypted_file = tmp_path / ".env.enc"
    input_file.write_text("VALUE=ok\n")

    envcrypt.main(
        [
            "--encrypt",
            "--rm",
            "--password",
            PASSWORD,
            str(input_file),
            str(encrypted_file),
        ]
    )

    assert not input_file.exists()
    assert encrypted_file.exists()
