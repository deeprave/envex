#!/usr/bin/env python3
"""
Block data encryption using
"""

import os
import sys
import logging
import string
from io import BytesIO
from pathlib import Path

from envex.env_crypto import encrypt_data, decrypt_data, DecryptError

ENCRYPTED_EXT = ".enc"

logging.basicConfig(
    format="%(asctime)s %(levelname).3s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__file__)


def check_password_simple(password: str) -> bool:
    """
    Check if a password is too simple based on length,
    character variety, and basic complexity rules.
    Returns True if the password is too simple.
    """
    # Minimum length check
    if len(password) < 8:
        return True

    # Check for character variety
    has_upper = any(char.isupper() for char in password)
    has_lower = any(char.islower() for char in password)
    has_digit = any(char.isdigit() for char in password)
    all_digit = all(char.isdigit() for char in password)
    has_special = any(char in string.punctuation for char in password)

    if not has_upper or not has_lower or not has_digit or not has_special or all_digit:
        return True

    # Check for repeated/sequential characters
    if len(set(password)) <= 3:  # Mostly repeated characters
        return True

    repeated_patterns = ["12345", "abcde", "password", "qwerty", "asdf"]
    return any((pattern in password.lower() for pattern in repeated_patterns))


def main():
    import io
    import argparse

    class CustomParser(argparse.ArgumentParser):
        def error(self, message):
            logger.error(f"{self.prog}: error: {message}")
            super().error()

        def warning(self, message):
            logger.warning(f"{self.prog}: error: {message}")
            super().warning()

        def print_help(self, file=None):
            text = io.StringIO()
            super().print_help(file=text)
            text.seek(0)
            for line in text.readlines():
                logger.info(line.strip())

    class CustomHelpFormatter(argparse.ArgumentDefaultsHelpFormatter):
        def __init__(self, *args, **kwargs):
            kwargs["max_help_position"] = 45
            kwargs["width"] = 1000
            super().__init__(*args, **kwargs)

    parser = CustomParser(description=__doc__, formatter_class=CustomHelpFormatter)
    password_opts = parser.add_mutually_exclusive_group()
    password_opts.add_argument(
        "-P", "--password", action="store", help="Use given password"
    )
    password_opts.add_argument(
        "-E",
        "--environ",
        action="store",
        help="Read password from provided environment variable",
    )
    password_opts.add_argument(
        "-F", "--file", action="store", help="Read password from a given file"
    )

    encrypt_opts = parser.add_mutually_exclusive_group()
    encrypt_opts.add_argument(
        "-e", "--encrypt", action="store_true", default=False, help="Use given password"
    )
    encrypt_opts.add_argument(
        "-d",
        "--decrypt",
        action="store_true",
        default=False,
        help="Read password from provided environment variable",
    )

    parser.add_argument(
        "-r",
        "--rm",
        action="store_true",
        default=False,
        help="Remove input file after successful conversion",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Increase output verbosity",
    )
    parser.add_argument("input", action="store", help="File to encrypt or decrypt")
    parser.add_argument(
        "output", nargs="?", default=None, action="store", help="Output file (optional)"
    )

    args = parser.parse_args()

    if not (_password := args.password):
        if args.environ:
            _password = os.environ.get(args.environ)
        elif args.file:
            _password = Path(args.file).read_text()
        else:
            logger.error(f"{parser.prog}: password or password source is not provided")
            exit(2)

    if check_password_simple(_password):
        logger.warning("""WARNING: Password appears to be too short, simple or can easily be guessed.
  Recommended:
    - at least 1 each of uppercase, lowercase, digit, punctuation
    - at least 8 characters in length
    - does not contain common sequences used in passwords""")

    if not args.encrypt and not args.decrypt:
        logger.error(
            "{parser.prog}: operation to perform (--encrypt or --decrypt) must be specified"
        )
        exit(3)

    encrypt = args.encrypt

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    _input = Path(args.input)
    if not _input.exists():
        logger.error(f"{parser.prog}: {_input} does not exist")
        exit(1)

    if not args.output:
        if encrypt:
            args.output = f"{args.input}{ENCRYPTED_EXT}"
        elif args.input.endswith(ENCRYPTED_EXT):
            args.output = args.input[: -len(ENCRYPTED_EXT)]
        else:
            logger.error(
                f"{parser.prog}: cannot automatically determine output file name"
            )
            exit(1)

    _output = Path(args.output)
    if _output.exists() and _input.samefile(_output):
        logger.error(f"{parser.prog}: Input and Output files cannot be the same")
        exit(1)

    logger.debug(
        f"{parser.prog}: {'encrypt' if encrypt else 'decrypt'} {_input} -> {_output}"
    )

    func = encrypt_data if encrypt else decrypt_data
    try:
        _output.write_bytes(func(BytesIO(_input.read_bytes()), _password).getvalue())
    except DecryptError as e:
        logger.error(f"{parser.prog}: {e.args}")
        exit(4)

    if args.rm:
        logger.debug(f"{parser.prog}: removing {_input}")
        _input.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
