.PHONY: test lint serve build docker clean

test:
	pytest tests/ -v

lint:
	ruff check .

serve:
	uvicorn server:app --reload --port 8000

build:
	pip install build && python -m build

docker:
	docker build -t abaqus-agent .

docker-up:
	docker compose up -d

clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache coverage.xml
