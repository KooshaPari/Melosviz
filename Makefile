# MelosViz — top-level Makefile
# Companion self-check surface for MV-FR-50.

.PHONY: diagnose test-backend lint-backend golden harbor a11y-fixture trace wbs gap-matrix journeys timing-budgets repro-smoke hermetic-smoke hermetic-python-smoke portability-smoke sdk-pack-smoke flaky-quarantine sdk-publish-dry-run dev-up dev-down dev-pipeline dev-logs viz-install viz-demo viz-offline-demo

diagnose:
	python3 scripts/diagnose.py

test-backend:
	cd backend && python -m pytest -q

lint-backend:
	cd backend && python -m ruff check src/ tests/ && python -m ruff format --check src/ tests/

golden:
	cd backend && python -m pytest tests/test_golden_corpus.py -q

timing-budgets:
	python3 scripts/check_timing_budgets.py

repro-smoke:
	bash scripts/check_repro_smoke.sh

hermetic-smoke:
	bash scripts/check_hermetic_smoke.sh

hermetic-python-smoke:
	bash scripts/check_hermetic_python_smoke.sh

portability-smoke:
	python3 scripts/check_portability_smoke.py

sdk-pack-smoke:
	bash scripts/check_sdk_pack_smoke.sh

sdk-publish-dry-run:
	MELOSVIZ_SDK_PUBLISH_DRY_RUN=1 bash scripts/publish_sdk_packages.sh

harbor:
	python3 eval/harbor/adapter.py --out eval/harbor/out

a11y-fixture:
	@echo "Open web/a11y/fixture.html via: python3 -m http.server 8760 --directory web/a11y"

wbs:
	python3 scripts/check_wbs.py

gap-matrix:
	python3 scripts/check_gap_matrix.py

journeys:
	python3 scripts/check_journeys.py

flaky-quarantine:
	python3 scripts/check_flaky_quarantine.py

trace: wbs gap-matrix journeys flaky-quarantine
	python3 backend/scripts/check/check_traceability.py

# --- Dev environment (ComfyUI worker + C4D stub + bridge) ----------------

dev-up:
	docker compose -f deploy/docker-compose.dev.yml up -d --build

dev-down:
	docker compose -f deploy/docker-compose.dev.yml down

dev-logs:
	docker compose -f deploy/docker-compose.dev.yml logs -f --tail=200

# Run the C4D stub server on its own (without docker compose). Useful for
# local dev when you want to point the orchestrator at a C4D endpoint but
# don't have a real Cinema 4D install + listener.
dev-c4d-stub:
	@mkdir -p ./out/c4d_stub_renders
	MELOSVIZ_C4D_OUTPUT_DIR=./out/c4d_stub_renders \
	  python3 -m uvicorn deploy.scripts.c4d_stub_server:app \
	    --host 127.0.0.1 --port 8787

# Test the C4D stub server (health + render + jobs).
dev-c4d-stub-test:
	python3 deploy/scripts/test_c4d_stub_server.py

dev-pipeline:
	@bash deploy/scripts/run_pipeline_dev.sh

# --- Zero-dependency offline demo (no GPU, no ComfyUI, no Docker) ---------

PYTHON ?= python3

viz-install:
	@command -v uv >/dev/null 2>&1 || { echo "uv not found — install from https://docs.astral.sh/uv/"; exit 1; }
	@if [ ! -d .venv ]; then uv venv --python 3.12 .venv; fi
	@. .venv/bin/activate && uv pip install -e backend/ pytest
	@echo "Installed. Activate with:  source .venv/bin/activate"

viz-demo: viz-install
	@. .venv/bin/activate && bash scripts/demo_offline.sh /tmp/melosviz-demo

viz-offline-demo:
	@. .venv/bin/activate && bash scripts/demo_offline.sh /tmp/melosviz-demo

# Clean the offline demo artifacts (artefacts under /tmp).
viz-demo-clean:
	rm -rf /tmp/melosviz-demo

