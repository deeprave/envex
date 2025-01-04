# ChangeLog

### v4.1.0

- enhance password resolution and environment handling
- added ENV_PASSWORD, $ENV_PASSWORD and @ENV_PASSWORD vars to automatically trigger decryption

### v4.0.0

- :warning: BREAKING CHANGE: additional kwargs passed to Env() are no longer added to the env if readenv=False. This is probably of no consequence as it is a (mis?)feature that was rarely (if ever) used.
- Bugfix: dicts passed in *args the Env() are now correctly converted to str->str mappings.
- Feature: Env can now take BytesIO and StringIO objects in Env(*args). Since these are immediate objects, they are handled as priority variables, different to variables set via `.env` files in that they overwrite existing variables by default. Explicitly using the overwrite=False changes this behaviour.
- Warning: To provide support for different types of streams, environment files are now handled internally as bytes. However, before evaluation they are converted via an encoding parameter that defaults to "utf-8".
- Feature: Encrypted `.env` files (`.env.enc`) are now supported. You no longer need to implement a Hashicorp Vault in order to avoid having plain text secrets on the filesystem, you can simply encrypt the `.env` file directly. Use the `decrypt=True` parameter and provide the encryption pass phrase used to derive the key:

  - `password=<pass-phrase>`
  - `password=$<environment_variable_name>`
  - `password=/<filename to read>`
-  Feature: Encrypted `.env` files (`.env.enc`) are now supported. You no longer need to implement a Hashicorp Vault in order to avoid having plain text secrets on the filesystem, you can simply encrypt the `.env` file directly. Use the `decrypt=True` parameter and provide the password used to derive the key.
- A utility cli script `envcrypt` is provided to support both encryption and decryption. Use `envcrypt -h` for usage.

### v3.2.0

- upgrade dependencies (several) including vulnerability fixes
- (dev) combined test & development dependency groups

### v3.1.2

- dependency updates
- minor logging tweaks
- iron out some warts

### v3.1.1

- Add testcontainers for development
- Add integration test to test against a "real"  (testcontainers) Vault
- Improve test coverage

### v3.1.0

- Replace many pre-commit hooks with ruff
- Use a separate configuration file `ruff.toml` for ruff with only local tweaks in `pyproject.toml`

### v3.0.4

- Add timeout configuration to secretsmangager client and default 5s to reduce wait time when vault is unavailable. May be overridden in code or using the VAULT_TIMEOUT environment variable.
- exclude example files from guardian scanning
- github workflow changes

### v3.0.0

- Reduced complexity in vault secrets caching, now simply caches all secrets as a single dict.
  If non-empty, the cache is always used to return individual values with the assumption that
  the vault secrets remain unchanged during the lifetime of the process, which is the intended
  use case.
- Use <mount_point>/data/<base_path> for secret values, vault kv store compatible.
- client.write **kwargs to generate the POST api request correctly (previously not working)
- rewrote and simplified vault secrets related tests using pytest parameterization
- add `envsecrets` script, used to split a .env into persistent values and inject secrets into vault
  based on a template. provide an example of how this might be used.

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
