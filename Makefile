# MelosViz — top-level Makefile
# Companion self-check surface for MV-FR-50.

.PHONY: diagnose test-backend lint-backend golden harbor a11y-fixture trace wbs gap-matrix journeys timing-budgets repro-smoke hermetic-smoke

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

trace: wbs gap-matrix journeys
	python3 backend/scripts/check/check_traceability.py

