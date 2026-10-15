# python-package-template

A Python package template with strict typing, eight checks and CI wired in from the first commit.

`make checks` runs the same checks on your machine that CI runs on every push, so a pull request fails for the same
reason in both places.

## Start a package

1. Click **Use this template** on GitHub, or run:

   ```bash
   gh repo create acme-widgets --template jpsanders/python-package-template --private --clone
   cd acme-widgets
   ```

2. Rename the package. This replaces the template's import name and command name in every tracked file and moves the
   package and test folders:

   ```bash
   make rename NAME=acme_widgets
   ```

3. In a virtual environment with Python 3.12 or later, install the development tools and run every check:

   ```bash
   make init-dev
   make checks
   ```

`make init` installs the package on its own, without the development tools.

## The checks

| Check | Tool | What it stops |
| --- | --- | --- |
| Formatting | black, 120 columns | Style arguments in review |
| Import order | isort, black profile | Noisy diffs from reordered imports |
| Whitespace | editorconfig-checker | Tabs, trailing spaces, missing final newlines and long lines, in every file type |
| Docstrings | darglint, Sphinx style | A docstring that documents parameters the function no longer takes |
| Lint | flake8 with pydocstyle and tidy-imports | Unused imports and names, docstring style errors, relative imports |
| Types | mypy, strict | Untyped functions and silent `Any` |
| Security | bandit | Shell injection, unsafe deserialisation, hardcoded passwords |
| Tests | pytest with coverage | Regressions, with a coverage report on every run |

`make checks` only reports. `make format` applies black and isort. `make help` lists every target.

## Layout

```text
src/python_template/      the package, with py.typed so type checkers trust its hints
tests/python_template/    pytest tests, mirroring the package
scripts/rename.py         the one time rename
.github/workflows/        CI, built from reusable workflows
Dockerfile                an image built from source, running without root
Makefile                  every command in this file
```

## Versions

There is no version number in the code. setuptools_scm reads it from git. Tag a commit `v0.1.0` and `make build` writes
a 0.1.0 wheel to `build/dist`. Untagged commits build as development versions such as `0.1.dev3+g1a2b3c4`.

## CI

`dev.yml` runs on every push to `main` and on every pull request.

- **lint** runs the seven static checks.
- **test** runs pytest on Python 3.12, 3.13 and 3.14.
- **test_with_db** runs pytest next to a Postgres 16 service with three empty schemas, for packages that talk to a
  database.
- **rename** renames the package to `acme_widgets` and runs every check again. It proves that a new repository made from
  the template starts green.

The building blocks are reusable workflows with inputs, so a single check can be switched off, for example with
`enable-bandit: false`. To install dependencies from a private package index, store the index URL with its credentials
as the `PKG_REPOSITORY` secret. CI passes it to pip as an extra index.

## Docker

```bash
make build-docker
docker run --rm python-template:latest
```

The image runs as an unprivileged user. The build mounts `.git` read only so setuptools_scm can version the install,
which needs BuildKit, the default builder in current Docker.

## Notes

Files that belong to one developer, such as `.envrc` or `.python-version`, go in your global ignore file,
`~/.gitignore`. The repository's `.gitignore` lists only what the code itself produces.

Issues and pull requests are welcome.

[James Phillip Sanders](https://jamesphillipsanders.com)

## License

MIT
