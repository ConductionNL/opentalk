.PHONY: help build push run clean lint format lint-fix format-fix mypy check check-strict

APP_ID = opentalk
REGISTRY = ghcr.io
IMAGE = conductionnl/$(APP_ID)-exapp
VERSION ?= latest

help:
	@echo "$(APP_ID) ExApp"
	@echo ""
	@echo "  make build         Build the Docker image"
	@echo "  make push          Push it to $(REGISTRY)"
	@echo "  make run           Run the container locally (interactive; asserts nothing)"
	@echo "  make clean         Remove the local image"
	@echo ""
	@echo "  make lint          ruff check ex_app/"
	@echo "  make format        ruff format --check ex_app/"
	@echo "  make mypy          mypy ex_app/"
	@echo "  make check         lint + mypy"
	@echo "  make check-strict  lint + format + mypy"
	@echo ""
	@echo "There is NO 'make test' target. This repo has no automated test"
	@echo "suite of any kind, and a target that pretends otherwise is worse"
	@echo "than its absence. 'make run' is what used to be called 'make test':"
	@echo "an interactive 'docker run -it' that boots the container and"
	@echo "asserts nothing."

build:
	docker build -t $(REGISTRY)/$(IMAGE):$(VERSION) .

push: build
	docker push $(REGISTRY)/$(IMAGE):$(VERSION)

# Renamed from `test`. It never tested anything — it starts the container
# interactively and makes no assertion, and cannot run in CI at all (-it needs
# a TTY). Calling that `test` is the same defect as `|| echo skipping`: a
# command whose name claims a verdict it never reaches.
run:
	docker run --rm -it \
		-e APP_ID=$(APP_ID) \
		-e APP_VERSION=0.1.0 \
		-e APP_SECRET=test \
		-e NEXTCLOUD_URL=http://localhost \
		-p 9000:9000 \
		$(REGISTRY)/$(IMAGE):$(VERSION)

clean:
	docker rmi $(REGISTRY)/$(IMAGE):$(VERSION) || true

# ── Python quality ──────────────────────────────────────────────────────────
# The application is ex_app/lib/main.py. Until 2026-08-05 nothing in this repo
# looked at it: the static-analysis stack (phpcs/psalm/phpstan/phpmd) is aimed
# at phpcs-custom-sniffs/, and code-quality.yml ran only the PHP legs.
# Install the tools with: pip install -r requirements-dev.txt

lint:
	ruff check ex_app/

format:
	ruff format --check ex_app/

lint-fix:
	ruff check --fix ex_app/

format-fix:
	ruff format ex_app/

mypy:
	mypy ex_app/

check:
	@E=0; \
	for CMD in lint mypy; do \
		echo; echo "=== $$CMD ==="; \
		$(MAKE) --no-print-directory $$CMD || E=1; \
	done; \
	echo; \
	if [ $$E -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "SOME CHECKS FAILED (see above)"; fi; \
	exit $$E

check-strict:
	@E=0; \
	for CMD in lint format mypy; do \
		echo; echo "=== $$CMD ==="; \
		$(MAKE) --no-print-directory $$CMD || E=1; \
	done; \
	echo; \
	if [ $$E -eq 0 ]; then \
		echo "ALL CHECKS PASSED - STATIC ANALYSIS ONLY."; \
		echo "This green covers ruff (lint + format) and mypy over ex_app/."; \
		echo "It says NOTHING about behaviour: this repo has no automated test"; \
		echo "suite - no pytest config, no test_*.py, no phpunit.xml, no tests/."; \
		echo "Do not add a test target until a real suite exists."; \
	else \
		echo "SOME CHECKS FAILED (see above)"; \
	fi; \
	exit $$E
