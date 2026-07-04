# MelosViz — top-level Makefile
# Companion self-check surface for MV-FR-50.

.PHONY: diagnose

diagnose:
	python3 scripts/diagnose.py
