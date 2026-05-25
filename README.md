[![Maintenance](https://img.shields.io/badge/maintenance-active-brightgreen.svg)](https://github.com/deeprave/envex)
[![PyPI version](https://img.shields.io/pypi/v/envex.svg?logo=pypi&logoColor=white)](https://pypi.org/project/envex)
[![PyPI downloads](https://img.shields.io/pypi/dm/envex.svg?logo=pypi&logoColor=white)](https://pypi.org/project/envex)
[![Python versions](https://img.shields.io/pypi/pyversions/envex.svg?logo=python&logoColor=white)](https://pypi.org/project/envex)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
# ENV EXtended

`envex` is a dotenv `.env` aware environment variable handler with typing features and HashiCorp Vault support.

## Overview

This module offers a convenient interface for managing application environments and configurations while adhering to the [12-factor app methodology](https://12factor.net). It avoids having any environment-specific variables and security-sensitive data within application code.

An `Env` instance delivers a lot of functionality by providing a type-smart front-end to `os.environ`, providing a superset of `os.environ` functionality.

## Installation

```shell
pip install envex
```

`envex` supports Python 3.12 through 3.14.

## Features

In addition to the standard `os.environ` functionality with automatic type conversion, `envex` provides the following features:

#### Supports AES-256 encrypted environment files
When enabled with the `decrypt=True` argument and provided with the decryption password `envex` searches for `.env.enc` files first but falls back to `.env`.
Using encrypted environment files avoids using plain text files on the filesystem that contain sensitive information.
The provided `envcrypt` utility conveniently allows conversion between encrypted and non-encrypted formats.

#### Vault support
Alternatively, `envex` provides seamless integration with HashiCorp Vault. This reduces the need to store plaintext secrets on the filesystem and provides a more secure approach for managing secrets.
HashiCorp Vault functionality is optional, and is activated automatically when the `hvac` module is installed into the active virtual environment, and where connection and authentication to Vault succeed.
Values fetched from Vault are cached by default to reduce the overhead of the api call.
If this is of concern, caching can be disabled using the`enable_cache=False` parameter to Env.

#### Extended variables
`envex` provides many features not available in other dotenv handlers (python-dotenv, etc.) including recursive
expansion of "template" style variables, supporting don't-repeat-yourself (DRY) patterns.

`envex` provides multiple ways to fetch environment variables:
```python
from envex import env

assert env['HOME'] == '/Users/username'

env['TESTING'] = 'This is a test'
assert env.get('TESTING') == 'This is a test'
assert env['TESTING'] == 'This is a test'
assert env('TESTING') == 'This is a test'
```

It provides the ability to set variable defaults without overriding, much the same as a standard python dict:
```python
import os

assert os.environ['TESTING'] == 'This is a test'

assert env.get('UNSET_VAR') is None
env.set('UNSET_VAR', 'this is now set')
assert env.get('UNSET_VAR') is not None
env.setdefault('UNSET_VAR', 'and this is a default value but only if not set')
assert env.get('UNSET_VAR') == 'this is now set'
env.set('UNSET_VAR', None)
assert env.get('UNSET_VAR') is None
del env['UNSET_VAR']
assert env.get('UNSET_VAR') is None
```

Note that there is a subtle difference between
- `env.get(<variable>, default=<default value>)` and
- `env(<variable>, default=<default value>)`.
If the variable is initially unset, the former simply returns the default value or None,
but the second also sets the value to the default value if one was provided in the environment, unless it was already set.

An Env instance can also read a `.env` (the default name) file and update the application environment accordingly.
It can read this either when created with `Env(readenv=True)` or directly by using the method `read_env()`.
If provided, the `readenv=True` parameter enable reading environment files according to the search_path
provided (the current directory by default) and the `parents=True` parameter extends the search to parent directories should the initial target not be found.

To override the default name of the environment file, use the `DOTENV` environment variable.

Variables in environment files will not overwrite existing environment variables by default. `overwrite=True` must be used to change this behaviour.

Env can also be passed one or more BytesIO or String IO objects as positional parameters from which to read environment variables are read as though they were files.
IO objects passed in this way differ only in that by default variables evaluated from their content overwrites existing
variables as though `overwrite=True` was used. To change the default behaviour, explicitly use `overwrite=False`.

Other kwargs that can be passed to `Env` when created:

* environ (env): pass the environment to update, default is os.environ, passing an empty dict will create a new env
* readenv (bool): search for and read .env files (default is False)
* env_file (str): name of the env file, `os.environ["DOTENV"]` if set, or `.env` is the default
* search_path (str or list): a single path or list of paths to search for the env files
  search_path may also be passed as a colon-separated list (or semicolon on Windows) of directories to search.
* parents (bool): search (or not) parents of dirs in the search_path
* overwrite (bool): overwrite already set values read from .env, default is to only set if not currently set
* update (bool): push update to os.environ if true (default) otherwise changes internally only
  note that the presence of "export" in the .env file will override this individually and the value will be exported
* working_dirs (bool): add CWD for the current process and PWD of source .env file
* exception: (optional) Exception class to raise on error (default is `KeyError`)
* errors: bool whether to raise error on missing env_file (default is False)
* decrypt: bool whether to support decryption of encrypted env files (default is False)
* password: str the password, environment variable or file/path to use for decryption (see below)
* kwargs: (keyword args, optional) additional environment variables to add/override

In addition, Env supports a few HashiCorp Vault configuration parameters as well:

* url: (str, optional) vault url, default is `$VAULT_ADDR`
* token: (str, optional) vault token, default is `$VAULT_TOKEN` or content of `~/.vault-token`
* cert: (str or tuple, optional) path to a combined client certificate/key PEM file, or a `(cert, key)` tuple of separate PEM file paths
* verify: (bool, optional) whether to verify server cert (default is True)
* base_path: (optional) logical secrets base path, or "environment" for secrets (default is None).
* mount_point: (optional) Vault secrets engine mount point (default is `secret/`; values may be provided with or without slashes and are normalized internally).
* enable_cache: bool whether to cache values fetched from Vault (default is True)
  This is used to prefix the logical path to the secret, i.e. `f"{base_path}/key"`.

Some type-smart functions act as an alternative to `Env.get` and having to parse the result:
```python
from envex import env

env['AN_INTEGER_VALUE'] = 2875083
assert env.get('AN_INTEGER_VALUE') == '2875083'
assert env.int('AN_INTEGER_VALUE') == 2875083
assert env('AN_INTEGER_VALUE', type=int) == 2875083

env['A_TRUE_VALUE'] = True
assert env.get('A_TRUE_VALUE') == 'True'
assert env.bool('A_TRUE_VALUE') is True
assert env('A_TRUE_VALUE', type=bool) is True

env['A_FALSE_VALUE'] = 0
assert env.get('A_FALSE_VALUE') == '0'
assert env.int('A_FALSE_VALUE') == 0
assert env.bool('A_FALSE_VALUE') is False
assert env('A_FALSE_VALUE', type=bool) is False

env['A_FLOAT_VALUE'] = 287.5083
assert env.get('A_FLOAT_VALUE') == '287.5083'
assert env.float('A_FLOAT_VALUE') == 287.5083
assert env('A_FLOAT_VALUE', type=float) == 287.5083

env['A_LIST_VALUE'] = '1,"two",3,"four"'
assert env.get('A_LIST_VALUE') == '1,"two",3,"four"'
assert env.list('A_LIST_VALUE') == ['1', 'two', '3', 'four']
assert env('A_LIST_VALUE', type=list) == ['1', 'two', '3', 'four']
```

Environment variables are always stored as strings.
This is enforced by the underlying os.environ, but also true of any provided environment, which must use the `MutableMapping[str, str]` contract.

## Encrypted Environment Files

To enhance security of environment files that exist on the filesystem `envex` supports the creation and use of authenticated AES-256-GCM encrypted files.
Version 5.0.0 changes the encrypted file format from the legacy AES-CBC format to AES-GCM because the old format did not authenticate ciphertext and was vulnerable to padding-oracle style attacks if decryption failures were exposed.
The new format authenticates encrypted data before returning plaintext and is not subject to that vulnerability.

Encrypted `.env` files are named as `.env.enc` by default (strictly, `${DOTENV:-.env}.enc`), to distinguish them from the unencrypted version, but this is only by convention; both to distinguish the files visually, and to prevent other dot-env readers from using them.

If the feature is enabled and a passphrase is provided when the environment file is read, `envex` determines automatically if it contains encrypted data. If the `.enc` version of the environment file does not exist, the .env file - encrypted or not - is used as a fallback, but will otherwise be ignored.

### Version 5 Encrypted File Compatibility

This is a breaking encrypted-file format change:

- Files encrypted by envex 5.0.0 and later cannot be decrypted by envex 4.x or older.
- Envex 5.0.0 can still decrypt legacy AES-CBC files with explicit legacy mode so existing files can be migrated.
- Any file re-encrypted with envex 5.0.0 will require envex 5.0.0 or later to decrypt.
- Normal decryption rejects legacy AES-CBC files by default so a modified AES-GCM file cannot be downgraded into the unauthenticated legacy path.

To migrate an existing encrypted file, decrypt it with a version that can read the current file, then re-encrypt it with envex 5.0.0 or later:

```shell
envcrypt --decrypt --legacy --password "$PASSPHRASE" .env.enc .env
envcrypt --encrypt --password "$PASSPHRASE" .env .env.enc
```

If the passphrase is stored in an environment variable or file, use `--environ NAME` or `--file PATH` instead of `--password`.
After migration, verify the new file can be decrypted by envex 5.0.0 or later and remove any temporary plaintext file:

```shell
envcrypt --decrypt --password "$PASSPHRASE" .env.enc .env.verify
rm .env .env.verify
```

The `envcrypt` CLI utility supports the encryption and decryption of environment files.
```shell
usage: envcrypt.py [-h] [-P PASSWORD | -E ENVIRON | -F FILE] [-e | -d] [--legacy] [-r] [-v] input [output]

envcrypt: File encrypt/decrypt (authenticated AES-256-GCM)

positional arguments:
input                    File to encrypt or decrypt
output                   Output file (optional) (default: None)

options:
-h, --help               show this help message and exit

-P, --password PASSWORD  Use given password (default: None)
-E, --environ ENVIRON    Read password from provided environment variable (default: None)
-F, --file FILE          Read password from a given file (default: None)

-e, --encrypt            Encrypt input (default: False)
-d, --decrypt            Decrypt input (default: False)
--legacy                 Allow decrypting legacy AES-CBC files for migration (default: False)

-r, --rm                 Remove input file after successful conversion (default: False)
-v, --verbose            Increase output verbosity (default: False)

```
Either `--encrypt` or `--decrypt` must be provided

A passphrase is required, one of `--password`, `--environ`, or `--file` must also be given. If the passphrase is not provided, the utility will prompt for it stdin is available and is a terminal.

After an encryption or decryption operation, the input file is retained by default, but can be removed using the `--rm` option.

Specifying the output filename is optional, and if not given the utility will append `.enc` to the input filename for encryption, or remove `.enc` for decryption. The --rm option will remove the input file on success.

Note that similar to use of the Vault option, the value of encrypted variables is not published (exported) to the process environment unless the "export" prefix is used in the decrypted environment file, and therefore remains hidden from external processes.
However, the passphrase must be available in order for the environment to be read, and therefore the security of the encrypted file is only as strong as the security of that passphrase.

Three options are available when using the `Env` class to read encrypted environment files.
A value passed to the password parameter can be a string which is by default the plain text passphrase.
If it is prefixed by `$` then it reads the passphrase via the named environment variable, or if it is prefixed by `@` it is read read from a file.

### Benefits of Encrypted Environment Files

While slightly less convenient (having to manually encrypt and decrypt environment files), the benefits of using encrypted environment files are:

- Prevents sensitive data leakage from plaintext `.env` files.
- Ideal for use in shared or distributed systems.
- Mitigates risks associated with misconfigured access permissions.
- Provides an additional layer of security for sensitive data.

Also, encrypted .env files are not available to other .env aware software.

## Vault

In addition to handling of the os environment and .env files - encrypted or plain text - `envex` supports selectively fetching secrets from HashiCorp Vault using the kv.v2 engine.
This provides a secure secrets store, and completely avoids exposing secrets in plain text on the filesystem and in particular in published docker images.
It also prevents storing secrets in the operating system’s environment, which can be inspected by external processes.

This document does not cover how to set up and configure a Vault server, but you can find useful resources on the following websites:

- [hashicorp.com](https://developer.hashicorp.com/vault) for the developer documentation and detailed information and tutorials on setting up and hosting your own vault server, and
- [vaultproject.io](https://www.vaultproject.io/) for information about HashiCorp's managed cloud offering.

To access the Vault server, you need a token with a role that has read permission for the path to the secrets.
A read-only profile is the strongly recommended policy for tokens used at runtime by the application.

This library provides a utility called `env2hvac` that can import (create or update) a typical .env file into vault. The
utility stores one KV document per application and environment, using the logical path <appname>/<envname> - for example, myapp/prod - with .env keys stored inside that document. The utility requires that the token has a role with create or update permission for the target secrets path on the vault server.
By default, the utility uses the kv.v2 secrets engine mounted at `secret/`. A key such as `DB_PASSWORD` from `myapp/prod` is stored inside the KV document at logical path `myapp/prod`.

### Environment Variables

The SecretsManager and Vault client leverage environment variables for their configuration.
This ensures a degree of transparency as it allows the client to use them but mitigates the need for the client code to be aware of their presence.
A summary of these variables is in the following table:


| Variable          | Description                                                            |
| ----------------- | ---------------------------------------------------------------------- |
| VAULT_ADDR        | The URL of the vault server                                            |
| VAULT_TOKEN       | The vault token to use for authentication                              |
| VAULT_CACERT      | The path to the CA certificate to use for TLS verification             |
| VAULT_CAPATH      | The path to a directory of CA certificates to use for TLS verification |
| VAULT_CLIENT_CERT | The path to the client certificate PEM file, or a combined certificate/key PEM file for TLS client auth |
| VAULT_CLIENT_KEY  | The optional path to a separate client key PEM file for TLS client auth |
