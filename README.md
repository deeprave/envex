# ENV EXtended

`envex` is a dotenv `.env` aware environment variable handler with typing features and Hashicorp vault support.

[![PyPI version](https://badge.fury.io/py/envex.svg)](https://badge.fury.io/py/envex)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

## Overview

This module provides a convenient interface for handling the environment, and therefore configuration of any application
using 12factor.net principals removing many environment-specific variables and security sensitive information from
application code.

An `Env` instance delivers a lot of functionality by providing a type-smart front-end to `os.environ`,
providing a superset of `os.environ` functionality, including setting default values.

From version 2.0, this module also supports transparently fetching values from Hashicorp vault,
which reduces the need to store secrets in plain text on the filesystem.
This functionality is optional, activated automatically when the `hvac` module is installed, and connection and
authentication to Vault succeed.
Only get (no set) operations to Vault are supported.
Values fetched from Vault are cached by default to reduce the overhead of the api call.
If this is of concern to security, caching can be disabled using the `enable_cache=False` parameter to Env.

This module provides some features not supported by other dotenv handlers (python-dotenv, etc.) including recursive
expansion of template variables, which can be very useful for DRY.

```python
from envex import env

assert env['HOME'] == '/Users/username'

env['TESTING'] = 'This is a test'
assert env.get('TESTING') == 'This is a test'
assert env['TESTING'] == 'This is a test'
assert env('TESTING') == 'This is a test'

import os

assert os.environ['TESTING'] == 'This is a test'

assert env.get('UNSET_VAR') is None
env.set('UNSET_VAR', 'this is now set')
assert env.get('UNSET_VAR') is not None
env.setdefault('UNSET_VAR', 'and this is a default value but only if not set')
assert env.get('UNSET_VAR') == 'this is now set'
del env['UNSET_VAR']
assert env.get('UNSET_VAR') is None
```

Note that there is a subtle difference between `env.get(<variable>, default=<default value>)`
and `env(<variable>, default=<default value>)`.
If the variable is unset, the former simply returns the default value,
but the latter also sets the value to the default value in the environment.

An Env instance can also read a `.env` (default name) file and update the application environment accordingly.
It can read this either when created with `Env(readenv=True)` or directly by using the method `read_env()`.
To override the base name of the dot env file, use the `DOTENV` environment variable.
Other kwargs that can be passed to `Env` when created:

* environ (env): pass the environment to update, default is os.environ, passing an empty dict will create a new env
* readenv (bool): search for and read .env files
* env_file (str): name of the env file, `os.environ["DOTENV"]` if set, or `.env` by default
* search_path (str or list): a single path or list of paths to search for the env file
  search_path may also be passed as a colon-separated list (or semicolon on Windows) of directories to search.
* parents (bool): search (or not) parents of dirs in the search_path
* overwrite (bool): overwrite already set values read from .env, default is to only set if not currently set
* update (bool): push updates os.environ if true (default) otherwise pool changes internally only
* working_dirs (bool): add CWD for the current process and PWD of source .env file
* exception: (optional) Exception class to raise on error (default is `KeyError`)
* errors: bool whether to raise error on missing env_file (default is False)
* kwargs: (keyword args, optional) additional environment variables to add/override

In addition, Env supports a few HashiCorp Vault configuration parameters:

* url: (str, optional) vault url, default is `$VAULT_ADDR`
* token: (str, optional) vault token, default is `$VAULT_TOKEN` or content of `~/.vault-token`
* cert: (tuple, optional) (cert, key) path to client certificate and key files
* verify: (bool, optional) whether to verify server cert (default is True)
* cache_enabled: (bool, optional) whether to cache secrets (default is True)
* base_path: (optional) str base path, or "environment" for secrets (default is None).
  This is used to prefix the path to the secret, i.e. `f"/secret/{base_path}/key"`.

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
This is enforced by the underlying os.environ, but also true of any
provided environment, which must use the `MutableMapping[str, str]` contract.

## Vault

In addition to handling of the os environment and .env files, Env supports fetching secrets from Hashicorp Vault using
the kv.v2 engine.
This provides a secure secrets store, without exposing them in plain text on the filesystem and in particular in
published docker images.
It also prevents storing secrets in the operating system’s environment, which can be inspected by external processes.
Env can read secrets from the environment variables if you set Env(readenv=True).

This document does not cover how to set up and configure a vault server, but you can find useful resources on the
following websites:

- [hashicorp.com](https://developer.hashicorp.com/vault) for the developer documentation and detailed information and
  tutorials on setting up and hosting your own vault server, and
- [vaultproject.io](https://www.vaultproject.io/) for information about HashiCorp's managed cloud offering.

To access the vault server, you need a token with a role that has read permission for the path to the secrets.
A read only profile is the recommended policy for tokens used at runtime by the application.

This library provides a utility called `env2hvac` that can import (create or update) a typical .env file into vault. The
utility uses a prefix that consists of an application name and an environment name, using the
format <appname>/<envname>/<key> - for example, myapp/prod/DB_PASSWORD. The utility requires that the token has a role
with create permission for the base secrets path on the vault server.
The utility currently assumes that the kv secrets engine is mounted at secret/. The
final path where the secrets are stored will be secret/data/<appname>/<envname>/<key>.
