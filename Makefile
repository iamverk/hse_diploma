.PHONY: demo test compile

PYTHON ?= python

demo:
	PYTHON="$(PYTHON)" bash demo/run_demo.sh

test:
	$(PYTHON) -m pytest tests/test_assignment.py tests/test_agent_judge.py tests/test_reporting.py

compile:
	$(PYTHON) -m py_compile tools/assignment.py tools/agent_judge.py tools/reporting.py tools/render_tree.py tools/render_thesis_figures.py tools/metrics_v2.py
