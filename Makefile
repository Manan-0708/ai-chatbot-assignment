.PHONY: up down build test clean logs

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

test:
	pytest backend/tests -v

logs:
	docker compose logs -f

clean:
	docker compose down -v
