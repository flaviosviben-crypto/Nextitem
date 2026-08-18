.PHONY: help install dev backend frontend test build docker clean

help:
	@echo "make install   Install backend and frontend dependencies"
	@echo "make dev       Run backend and frontend together"
	@echo "make backend   Run the API on :8000"
	@echo "make frontend  Run the web app on :3000"
	@echo "make test      Run the backend test suite"
	@echo "make build     Production build of the frontend"
	@echo "make docker    docker compose up --build"

install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

backend:
	cd backend && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

dev:
	@echo "Starting API on :8000 and web on :3000 — Ctrl-C stops both."
	@(cd backend && uvicorn app.main:app --port 8000 &) ; \
	 cd frontend && npm run dev

test:
	cd backend && python -m pytest tests/ -q

build:
	cd frontend && npm run build

docker:
	docker compose up --build

clean:
	rm -rf frontend/.next backend/var backend/**/__pycache__
