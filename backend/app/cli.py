"""CLI administrativa: python -m app.cli <comando>"""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.logging import setup_logging


def cmd_seed(_args) -> None:
    from app.seeds import seed

    with SessionLocal() as db:
        print(json.dumps(seed(db), ensure_ascii=False))


def cmd_create_admin(args) -> None:
    from app.core.security import hash_password
    from app.models import User

    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == args.email.lower()))
        if u:
            u.password_hash, u.role, u.is_active = hash_password(args.password), "admin", True
        else:
            db.add(User(email=args.email.lower(), name=args.name, role="admin", password_hash=hash_password(args.password)))
        db.commit()
        print("ok")


def cmd_example_channel(args) -> None:
    """Cria um canal de EXEMPLO (configuração), explicitamente nomeado como tal."""
    from app.models import Channel, ChannelEngine, ContentEngine

    with SessionLocal() as db:
        if db.scalar(select(Channel).where(Channel.slug == "canal-exemplo")):
            print("canal-exemplo já existe")
            return
        ch = Channel(name="Canal Exemplo", slug="canal-exemplo", niche="histórias animadas", language="pt-BR", region="BR",
                     description="Canal de exemplo criado pela CLI para testar o fluxo. Edite ou exclua.",
                     target_audience="jovens e adultos brasileiros 16-35", visual_style=args.style, autonomy_mode="assisted",
                     require_approval=True, videos_per_day=1, default_duration_s=40, platforms=["youtube", "tiktok", "instagram"])
        db.add(ch)
        db.flush()
        for e in db.scalars(select(ContentEngine)).all():
            db.add(ChannelEngine(channel_id=ch.id, engine_id=e.id, weight=1.0, initial_weight=1.0))
        db.commit()
        print(f"canal criado: id={ch.id}")


def cmd_produce(args) -> None:
    """Executa uma produção completa de forma síncrona (útil para testar o servidor)."""
    from app.core.config import settings

    settings.celery_eager = True
    from app.models import Channel, ContentEngine, ProductionJob
    from app.pipeline.orchestrator import advance, create_production
    from app.services import trends
    from app.services.ideas import generate_ideas

    with SessionLocal() as db:
        ch = db.get(Channel, args.channel) if args.channel else db.scalar(select(Channel).order_by(Channel.id))
        if not ch:
            sys.exit("Nenhum canal. Rode: python -m app.cli example-channel")
        eng = db.scalar(select(ContentEngine).where(ContentEngine.key == args.engine))
        if args.research:
            print("tendências:", trends.research(db))
        ideas = generate_ideas(db, channel_id=ch.id, engine_id=eng.id, count=3)
        idea = max(ideas, key=lambda i: i.total_score) if ideas else None
        print("ideia:", idea.title if idea else None)
        job = create_production(db, channel_id=ch.id, engine_id=eng.id, idea_id=idea.id if idea else None, autostart=False)
        jid = job.id
    print("resultado:", advance(jid))
    with SessionLocal() as db:
        job = db.get(ProductionJob, jid)
        print(json.dumps({"id": job.id, "status": job.status, "error": job.error, "output_asset_id": job.output_asset_id,
                          "qc": {k: job.qc_report.get(k) for k in ("passed", "fail_count", "warn_count")},
                          "simulated": job.simulated_parts, "cost_usd": job.actual_cost_usd}, ensure_ascii=False, default=str))


def main() -> None:
    setup_logging()
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed").set_defaults(fn=cmd_seed)
    a = sub.add_parser("create-admin")
    a.add_argument("--email", required=True)
    a.add_argument("--password", required=True)
    a.add_argument("--name", default="Administrador")
    a.set_defaults(fn=cmd_create_admin)
    e = sub.add_parser("example-channel")
    e.add_argument("--style", default="cartoon", choices=["stickman", "cartoon", "cinematic"])
    e.set_defaults(fn=cmd_example_channel)
    pr = sub.add_parser("produce")
    pr.add_argument("--channel", type=int)
    pr.add_argument("--engine", default="storytelling")
    pr.add_argument("--research", action="store_true")
    pr.set_defaults(fn=cmd_produce)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
