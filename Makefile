FERN := npx fern
SDKS_DIR := sdks
PYTHON ?= python3

.PHONY: generate fix-perms clean check test test-typescript test-python test-go test-php

# Regenerate SDKs in place using the locally-installed fern CLI (see package.json).
# `--force` overwrites generated files; anything listed in an SDK's .fernignore
# (e.g. the hand-written sbx.ts) is left untouched. No `rm -rf` here — deleting
# the tree first would wipe the preserved custom files before Fern runs.
generate:
	$(FERN) generate --local --force

# `fern generate --local` runs the generators in Docker, which on Linux can
# leave root-owned files in sdks/. Hand them back to the current user.
fix-perms:
	@if [ -n "$$(find $(SDKS_DIR) ! -user $$(id -u) -print -quit)" ]; then \
		sudo chown -R $$(id -u):$$(id -g) $(SDKS_DIR); \
	fi

# Remove only generated (git-ignored) files, keeping the committed custom bits.
clean:
	git clean -fdX $(SDKS_DIR)

# Validate the OpenAPI spec and Fern configuration.
check:
	$(FERN) check

# Build and test every SDK. Run `make generate` first.
test: test-typescript test-python test-go test-php

test-typescript:
	cd $(SDKS_DIR)/typescript && npm install --no-audit --no-fund && npm run build && npm test

test-python:
	cd $(SDKS_DIR)/python && $(PYTHON) -m pip install --quiet -e '.[test]' && $(PYTHON) -m pytest

test-go:
	cd $(SDKS_DIR)/go && go build ./... && go vet ./sbx/... && go test ./sbx/...

test-php:
	cd $(SDKS_DIR)/php && composer install --no-interaction --no-progress && composer build && composer test
