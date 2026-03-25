APP_NAME := $(notdir $(CURDIR))


# Default target
help:
	@echo "Dev Session Container - Available Commands:"
	@echo ""
	@echo "Environment Setup:"
	@echo "  make install          - Install code in the virtual environment"
	@echo ""
	@echo "Docker:"
	@echo "  make build            - Build docker image"


# Environment Setup
install:
	@echo "Installing CLI with uv inside venv..."
	uv pip install -e .

build:
	docker build -t ${APP_NAME} .
