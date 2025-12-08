SHELL := /bin/bash
VENV := "$(PWD)/../spec-venv/bin/activate"

.PHONY: smoke
smoke:
	@source $(VENV) && cd "$(PWD)" && python scripts/zk_smoke.py --runs 10 --csv data/results/zk_runs.csv

.PHONY: zk-scenarios
zk-scenarios:
	@source $(VENV) && cd "$(PWD)" && python scripts/run_scenarios.py --config configs/zk_scenarios.json

.PHONY: bm-user
bm-user:
	@source $(VENV) && cd "$(PWD)" && python scripts/bm_user_runner.py

.PHONY: bm-users
bm-users:
	@source $(VENV) && cd "$(PWD)" && python scripts/harness_multi.py --sessions 10 --csv data/results/bm_user_sessions.csv

.PHONY: contracts-test
contracts-test:
	@cd contracts && forge test -q
