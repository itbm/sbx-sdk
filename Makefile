FERN := $(shell which fern)
SDKS_DIR := sdks

.PHONY: generate clean

generate:
	sudo rm -rf $(SDKS_DIR)
	sudo -E $(FERN) generate --local --force
	sudo chown -R $(shell id -u):$(shell id -g) $(SDKS_DIR)

clean:
	rm -rf $(SDKS_DIR)
