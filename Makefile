FERN := npx fern
SDKS_DIR := sdks

.PHONY: generate clean

# Regenerate SDKs in place using the locally-installed fern CLI (see package.json).
# `--force` overwrites generated files; anything listed in an SDK's .fernignore
# (e.g. the hand-written sbx.ts) is left untouched. No `rm -rf` here — deleting
# the tree first would wipe the preserved custom files before Fern runs.
# NOTE: on Linux, `fern generate --local` may emit root-owned files (Docker);
# add `sudo chown -R $(shell id -u):$(shell id -g) $(SDKS_DIR)` if you hit that.
generate:
	$(FERN) generate --local --force

# Remove only generated (git-ignored) files, keeping the committed custom bits.
clean:
	git clean -fdX $(SDKS_DIR)
