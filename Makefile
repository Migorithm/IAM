export COMPOSE_DOCKER_CLI_BUILD=1
export DOCKER_BUILDKIT=1



checks:
	poetry run ./scripts/checks.sh

black:
	black -l 80 --preview $$(find * -name '*.py')

flake:
	flake8 $$(find * -name '*.py')
