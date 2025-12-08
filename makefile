.PHONY: smoke
smoke:
	@source "$(PWD)/spec-venv/bin/activate" && cd "$(PWD)" && python scripts/zk_smoke.py
