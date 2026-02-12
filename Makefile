.PHONY: preflight clean-ns

# Use virtual environment Python if it exists, otherwise fall back to system python3
PYTHON := $(shell if [ -d .venv ]; then echo .venv/bin/python; else echo python3; fi)

# virtual-default is where SimKube creates pods when trace uses namespace "default"
NS_PODS := virtual-default

preflight:
	$(PYTHON) ops/preflight.py

clean-ns:
	PYTHONPATH=. $(PYTHON) -c "from ops.hooks import run_hooks; run_hooks('pre_start', '$(NS_PODS)')"





