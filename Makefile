SRC := src
TESTS := tests
SCRIPTS := scripts
ROOT_EC_FILES := $(wildcard *.yaml *.yml *.md) .github
PACKAGE := python_template
DOCKER_IMAGE := python-template:latest

.PHONY: help
help:
	@echo "Available targets:"
	@grep -E "^([a-zA-Z_-]+):.*" $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":"}; {printf "    \033[36m%s\n\033[0m", $$1}'
	@echo ""
	@echo "Hints:"
	@echo "    Use '-n' to do a dry run"
	@echo "    Use '-k' to ignore failed targets and keep going"

.PHONY: create-egg-base
create-egg-base:
	@echo
	mkdir -p build/egg_base

.PHONY: init
init: create-egg-base
	@echo
	pip install -e .

.PHONY: init-dev
init-dev: create-egg-base
	@echo
	pip install -e .[dev]

.PHONY: format
format: black isort

.PHONY: isort-check
isort-check:
	@echo
	@echo --- Isort check ---
	isort --check --diff ${SRC} ${TESTS} ${SCRIPTS}

.PHONY: isort
isort:
	@echo
	@echo --- Isort auto format ---
	isort ${SRC} ${TESTS} ${SCRIPTS}

.PHONY: black-check
black-check:
	@echo
	@echo --- Black check ---
	black --check --diff ${SRC} ${TESTS} ${SCRIPTS}

.PHONY: black
black:
	@echo
	@echo --- Black auto format ---
	black ${SRC} ${TESTS} ${SCRIPTS}

.PHONY: ec
ec:
	@echo
	@echo --- Editorconfig linting checks ---
	ec ${SRC} ${TESTS} ${SCRIPTS} ${ROOT_EC_FILES}

.PHONY: docstyle
docstyle:
	@echo
	@echo --- Darglint docstring checks ---
	darglint -v 2 ${SRC} ${TESTS} ${SCRIPTS}

.PHONY: lint
lint:
	@echo
	@echo --- Flake8 linting checks ---
	flake8 ${SRC} ${TESTS} ${SCRIPTS}

.PHONY: mypy
mypy:
	@echo
	@echo --- Mypy type checks ---
	mypy ${SRC} ${TESTS} ${SCRIPTS}

.PHONY: pytest
pytest:
	@echo
	@echo --- Pytest regression and unit tests ---
	pytest --cov ${SRC}/${PACKAGE} ${TESTS}

.PHONY: bandit
bandit:
	@echo
	@echo --- Bandit security checks ---
	bandit -c pyproject.toml -f custom -r ${SRC} ${TESTS} ${SCRIPTS}

.PHONY: build
build: clean create-egg-base
	@echo
	@echo --- Build package wheel ---
	python -m build -o build/dist

# Rename the package once, right after creating a repository from the template
.PHONY: rename
rename:
	@test -n "$(NAME)" || (echo "usage: make rename NAME=your_package" && exit 1)
	python scripts/rename.py $(NAME)

.PHONY: build-docker
build-docker:
	@echo
	@echo --- Docker build image ---
	docker build -t ${DOCKER_IMAGE} --no-cache .

.PHONY: clean
clean:
	@echo
	rm -rf build/
	find ${SRC} ${TESTS} | grep -E "(\.egg-info|__pycache__|\.pyc|\.pyo$$)" | xargs rm -rf

# Run all checking tools
.PHONY: checks
checks: isort-check black-check ec docstyle lint mypy bandit pytest
