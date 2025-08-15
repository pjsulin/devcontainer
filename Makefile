APP_NAME := $(notdir $(CURDIR))


# Default target
help:
	@echo "Dev Session Container - Available Commands:"
	@echo ""
	@echo "Environment Setup:"
	@echo "  make install          - Install code in the virtual environment"      


# Environment Setup
install:
	@echo "Installing CLI with uv inside venv..."
	uv pip install -e .

build:
	@echo "Building docker container..."
	docker build -t ${APP_NAME} .
