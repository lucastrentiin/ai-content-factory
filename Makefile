.PHONY: up down logs ps build migrate test backend-dev frontend-dev backup restore admin

up:            ## sobe a stack completa
	docker compose up -d --build
down:
	docker compose down
logs:
	docker compose logs -f --tail=200 api worker beat
ps:
	docker compose ps
build:
	docker compose build
migrate:       ## aplica migrations e seeds
	docker compose run --rm api migrate
admin:         ## make admin EMAIL=x PASSWORD=y
	docker compose exec api python -m app.cli create-admin --email $(EMAIL) --password $(PASSWORD)
backup:        ## backup imediato
	docker compose exec -T db sh -c 'pg_dump -U $$POSTGRES_USER -d $$POSTGRES_DB --no-owner' | gzip > backups/manual_$$(date +%Y%m%d_%H%M%S).sql.gz
restore:       ## make restore FILE=backups/arquivo.sql.gz
	gunzip -c $(FILE) | docker compose exec -T db sh -c 'psql -U $$POSTGRES_USER -d $$POSTGRES_DB'
test:          ## testes do backend (requer PostgreSQL e Redis locais)
	cd backend && .venv/bin/pytest -q
backend-dev:
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000
frontend-dev:
	cd frontend && BACKEND_URL=http://localhost:8000 npm run dev
