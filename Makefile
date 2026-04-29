.PHONY: install test lint format clean

install:
	pip install -e .

test:
	pytest

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache