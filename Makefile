.PHONY: preflight clean-ns

# Use virtual environment Python if it exists, otherwise fall back to system python3
PYTHON := $(shell if [ -d .venv ]; then echo .venv/bin/python; else echo python3; fi)

preflight:
	$(PYTHON) ops/preflight.py

clean-ns:
	PYTHONPATH=. $(PYTHON) -c "from ops.hooks import run_hooks; run_hooks('pre_start', 'test-ns')"





