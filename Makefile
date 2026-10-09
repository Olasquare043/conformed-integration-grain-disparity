# Every target runs one pipeline stage through the CLI (python -m cigd <stage>),
# so each stage can also be run on its own without make.
#
#   make smoke            few-minute check on a tiny sample
#   make all              the full study
#   make all QUIET=1      the same, without progress bars (CI and Docker logs)

PYTHON ?= uv run --frozen python
PROFILE ?= full
QUIET ?= 0

# Fixed hash seed so set and dict ordering cannot change between runs.
export PYTHONHASHSEED := 0
export QUIET

CIGD = $(PYTHON) -m cigd --profile $(PROFILE)

.DEFAULT_GOAL := help
.PHONY: help all smoke check-sources data profile warehouse experiments test lint

help: ## List the available targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  %-15s %s\n", $$1, $$2}'

all: ## Run every stage of the full study in order
	$(CIGD) all

smoke: ## Run every stage on the tiny smoke sample
	$(PYTHON) -m cigd --profile smoke all

check-sources: ## Confirm every official source answers
	$(CIGD) check-sources

data: ## Download every source and check it against the frozen manifest
	$(CIGD) data

profile: ## Profile every source (results/tables/profile_*.csv, docs/data_profile.md)
	$(CIGD) profile

warehouse: ## Build the DuckDB warehouse: dimensions, facts and aggregates
	$(CIGD) warehouse

experiments: ## Run the pre-registered experiments (integration cost, coarse, fine)
	$(CIGD) experiments

test: ## Run the test suite against the built outputs
	$(CIGD) test

lint: ## Run ruff, nbstripout and the other pre-commit hooks on every file
	uv run --frozen pre-commit run --all-files
