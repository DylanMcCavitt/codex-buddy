PYTHON ?= python3
PORT ?= 47833
SERIAL_ARGS := --serial

ifdef SERIAL_PORT
SERIAL_ARGS := --serial-port $(SERIAL_PORT)
endif

.PHONY: bridge-serial bridge-dry-run test

bridge-serial:
	PYTHONPATH=src $(PYTHON) -u -m codex_buddy_bridge bridge $(SERIAL_ARGS) --port $(PORT)

bridge-dry-run:
	PYTHONPATH=src $(PYTHON) -u -m codex_buddy_bridge bridge --dry-run --port $(PORT)

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v
