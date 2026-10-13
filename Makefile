.PHONY: all database analysis test

PYTHON ?= python

all: database analysis

database:
	$(PYTHON) -m pipeline.build_database

analysis:
	$(PYTHON) -m pipeline.analyze

test:
	$(PYTHON) -m pytest -q
