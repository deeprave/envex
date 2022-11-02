************
env exTENDED
************

dotenv `.env` aware environment variable handling with typing features

Overview
--------

This is a refactoring of django-settings-env with Django specific functionality stripped out,
and so implements all of the smart environment handling suitable for use outside of Django.

This module provides a convenient interface for handling the environment, and therefore
configuration of any application using 12factor.net principals removing many environment specific
variables and security sensitive information from application code.

This module provides some features not supported by other dotenv handlers
(python-dotenv, etc.) including expansion of template variables which is very useful
for DRY.

An `Env` instance delivers a lot of functionality by providing a type-smart
front-end to `os.environ`, with support for most - if not all - `os.environ` functionality.
```python
from envex import env

assert env['HOME'] ==  '/Users/davidn'
env['TESTING'] = 'This is a test'
assert env['TESTING'] == 'This is a test'

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

An Env instance can also read a `.env` (default name) file and update the
application environment accordingly.

It can read this either from `__init__` or via the method `read_env()`.

* Override the base name of the dot env file, use the `DOTENV` environment variable.
* Other kwargs that can be passed to `Env.__init__`

  * env_file (str): base name of the env file, os.environ["DOTENV"] by default, or .env
  * search_path (str or list): a single path or list of paths to search for the env file
  * overwrite (bool): overwrite already set values read from .env, default is to only set if not currently set
  * parents (bool): search (or not) parents of dirs in the search_path
  * update (bool): update os.environ if true (default) otherwise pool changes internally
  * environ (env): pass the environment to update, default is os.environ

* Env() also takes an additional kwarg, `readenv` (default False) which instructs it to read dotenv files



Some type-smart functions act as an alternative to `Env.get` and having to
parse the result:
```python
from envex import env

env['AN_INTEGER_VALUE'] = 2875083
assert env.get('AN_INTEGER_VALUE') == '2875083'
assert env.int('AN_INTEGER_VALUE') == 2875083

env['A_TRUE_VALUE'] = True
assert env.get('A_TRUE_VALUE') == 'True'
assert env.bool('A_TRUE_VALUE') is True

env['A_FALSE_VALUE'] = 0
assert env.get('A_FALSE_VALUE') == '0'
assert env.int('A_FALSE_VALUE') == 0
assert env.bool('A_FALSE_VALUE') is False

env['A_FLOAT_VALUE'] = 287.5083
assert env.get('A_FLOAT_VALUE') == '287.5083'
assert env.float('A_FLOAT_VALUE') == 287.5083

env['A_LIST_VALUE'] = '1,"two",3,"four"'
assert env.get('A_LIST_VALUE') == '1,"two",3,"four"'
assert env.list('A_LIST_VALUE') == ['1', 'two', '3', 'four']
```

Note that environment variables are always stored as strings. This is
enforced by the underlying os.environ, but also true of any provided
environment, using the `MutableMapping[str, str]` contract.
