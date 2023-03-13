#!/bin/sh -e
set -x

poetry run bandit -r . -s B101,B105,B107 -x ./app/tests -lll
poetry run black .
poetry run ruff . 
poetry run mypy -p app --check-untyped-defs 