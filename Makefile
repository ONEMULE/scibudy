PYTHON ?= python3
VENV_PYTHON ?= .venv/bin/python
NPM ?= npm

.PHONY: test build-ui build-docs site-health package-check build-python bootstrap-smoke release-check

test:
	$(VENV_PYTHON) -m pytest -q

build-ui:
	cd web && $(NPM) run build

build-docs:
	$(VENV_PYTHON) -m mkdocs build --strict

site-health:
	$(VENV_PYTHON) scripts/check_site.py --base-url https://onemule.github.io/scibudy/

build-python:
	$(VENV_PYTHON) -m build

package-check:
	node --check bin/scibudy-install.mjs
	$(NPM) pack --dry-run

bootstrap-smoke:
	$(VENV_PYTHON) scripts/smoke_install.py --from-path . --profile base

release-check:
	$(VENV_PYTHON) scripts/release_check.py
