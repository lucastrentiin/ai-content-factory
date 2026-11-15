#!/bin/sh
set -e
wait_db() {
  i=0
  until pg_isready -d "$(echo "$DATABASE_URL" | sed 's/+psycopg//')" -q; do
    i=$((i+1)); [ $i -gt 60 ] && echo "Banco indisponível" && exit 1; sleep 2
  done
}
case "$1" in
  api)
    wait_db
    alembic upgrade head
    python -m app.cli seed
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --workers "${API_WORKERS:-2}"
    ;;
  worker)
    wait_db
    exec celery -A app.worker.celery_app worker -Q "${WORKER_QUEUES:-default,render}" -c "${WORKER_CONCURRENCY:-2}" --loglevel=INFO --max-tasks-per-child=50
    ;;
  beat)
    wait_db
    exec celery -A app.worker.celery_app beat --loglevel=INFO --schedule=/data/work/celerybeat-schedule
    ;;
  migrate)
    wait_db && alembic upgrade head && python -m app.cli seed
    ;;
  *)
    exec "$@"
    ;;
esac
