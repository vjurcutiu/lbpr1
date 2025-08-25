.PHONY: contracts lint-architecture setup

setup:
	python -m pip install --upgrade pip
	pip install pyyaml import-linter

contracts:
	python scripts/generate_contracts.py

lint-architecture:
	lint-imports --config=architecture/importlinter.ini || (echo "\n\nBoundary violation detected. See above." && exit 1)