.PHONY: preflight clean-ns

preflight:
	python3 ops/preflight.py

clean-ns:
	PYTHONPATH=. python3 -c "from ops.hooks import run_hooks; run_hooks('pre_start', 'test-ns')"





