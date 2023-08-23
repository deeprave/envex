# ChangeLog

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
