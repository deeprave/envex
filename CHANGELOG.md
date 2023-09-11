# ChangeLog

### v2.2.0

- Allow base_path to be set via env variable $VAULT_PATH.
- Add support for $VAULT_CLIENT_CERT and $VAULT_CLIENT_KEY

These changes allow full configuration of the secrets manager backend using the environment.

### v2.1.0

- Simplified and extended SecretsManager back-end
  - removed tie to kv secrets engine
  - add optional 'engine' param to Env/SecretsManager to determine path prefix, or override
  - add key delete, list methods
  - add vault seal handler, vault cli no longer required on host to unseal
  - add support for $VAULT_CACERT to specify CA certificate path

### v2.0.0

- Support for Hashicorp vault via a secrets manager
    - install optional "hvac" dependency to enable, else no-op
    - read hvac documentation for usage (eg VAULT_TOKEN and VAULT_ADDR)
    - by default, environment values override vault ones. To modify this
      behaviour, set ENVEX_SRC=vault to have vault values override.
      ENVEX_SRC=env by default.
    - args to Env() added to support vault client configuration
    - vault secrets are cached by default
    - base_path arg may be used to set a based vault path, i.e. f"/secret/{base_path}/key",
      allowing specific secrets to be used for different environments and roles

### v1.6.0

- revert to poetry for project management (.lock file used by dependabot)
- make working directory variables $CWD/$PWD optional (default=True)
- handle search_path parameter passed as an os.pathsep separated string
- clean up some internals
- allow passing a type as str in `__call__`, and optimise `__call__`
- reordered kwargs used in dot_env for consistency
- implemented pre-commit with ruff, black, isort

### v1.5.0

- handle "export" in .env files correctly - pass to os.environ if "export" is used
- also allow for other (as yet unimplemented) special commands or key=val prefixes

### v1.1.2

- ensure that env_path is resolved before updating $PWD

### v1.1.1

- updated `$PWD`/`$CWD` handling again, set these rather than setdefault to override possible
  values from the shell to provide more consistent results

### v1.1.0

- updated implied `$PWD` handling:
    - `$CWD` is setdefault for the process current directory (this was previously $PWD)
    - `$PWD` is setdefault for the directory containing the .env file
- errors: bool arg load_env and friends, defaults to False
    - if errors=True, FileNotFoundError is raised when no usable .env (`$DOTENV`) file is found
