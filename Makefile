.PHONY: install data report test lint site clean

install:
	pip install -r requirements-dev.txt

data:
	python -m src.simulate.campaign --config scenarios.yaml --out data/raw

report:
	python -m src.pipeline

test:
	pytest -q

lint:
	ruff check src tests

site:
	python -m http.server 8792 --directory site

clean:
	rm -rf data reports .pytest_cache
