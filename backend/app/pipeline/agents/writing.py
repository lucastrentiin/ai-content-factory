"""Agentes de escrita: Story Writer, Script Editor e Fact Checker."""
from __future__ import annotations

from sqlalchemy import or_, select

from app.models import Character, Episode, Idea, Location, Script, Series
from app.pipeline import prompts
from app.pipeline.context import StepContext
from app.providers.router import llm_json
from app.services.scripts import WORDS_PER_SECOND, add_version, estimated_duration, normalize_script


def _engine_dict(ctx: StepContext) -> dict:
    e = ctx.engine
    return {"name": e.name, "engine_type": e.engine_type, "description": e.description, "config": e.config or {}}


def _channel_dict(ctx: StepContext) -> dict:
    c = ctx.channel
    return {"name": c.name, "niche": c.niche, "target_audience": c.target_audience, "visual_style": c.visual_style,
            "language": c.language, "default_duration_s": c.default_duration_s}


def _series_context(ctx: StepContext) -> dict | None:
    if not ctx.job.series_id:
        return None
    s = ctx.db.get(Series, ctx.job.series_id)
    eps = ctx.db.scalars(select(Episode).where(Episode.series_id == s.id, Episode.status.in_(["produced", "published"]))
                         .order_by(Episode.number.desc()).limit(5)).all()
    current = ctx.db.get(Episode, ctx.job.episode_id) if ctx.job.episode_id else None
    return {"title": s.title, "synopsis": s.synopsis, "format": s.format, "story_bible": s.story_bible,
            "episode_number": current.number if current else None,
            "episode_plan": {"title": current.title, "synopsis": current.synopsis} if current else None,
            "previous_episodes": [{"number": e.number, "title": e.title, "summary": e.summary or e.synopsis,
                                   "hook_next": e.hook_next, "continuity": e.continuity} for e in reversed(eps)]}


def available_characters(ctx: StepContext, limit: int = 8) -> list[Character]:
    q = select(Character).where(Character.status == "active")
    conds = [Character.channel_id == ctx.channel.id, Character.is_shared.is_(True)]
    if ctx.job.series_id:
        s = ctx.db.get(Series, ctx.job.series_id)
        if s and s.universe_id:
            conds.append(Character.universe_id == s.universe_id)
    q = q.where(or_(*conds)).order_by(Character.role_type, Character.appearance_count.desc()).limit(limit)
    return list(ctx.db.scalars(q))


def story_writer(ctx: StepContext) -> dict:
    job = ctx.job
    idea = ctx.db.get(Idea, job.idea_id) if job.idea_id else None
    manual = (job.config or {}).get("manual_script")
    idea_d = ({"title": idea.title, "description": idea.description, "hook": idea.hook, "format": idea.format,
               "visual_style": idea.visual_style, "duration_s": idea.duration_s, "category": idea.category,
               **(idea.data or {})} if idea else {"title": job.title, "visual_style": job.visual_style})
    variant = (job.config or {}).get("variant")
    target = int(job.target_duration_s or ctx.channel.default_duration_s)
    limits = ctx.platform_limits()
    target = int(min(target, limits["max"] - 3))
    chars = available_characters(ctx)
    char_d = [{"name": c.name, "role": c.role_type, "personality": c.personality, "speech_style": c.speech_style,
               "catchphrases": c.catchphrases} for c in chars]
    locs = ctx.db.scalars(select(Location).where(Location.channel_id == ctx.channel.id).order_by(Location.reuse_count.desc()).limit(6)).all()
    loc_d = [{"name": loc.name, "setting_type": loc.setting_type, "time_of_day": loc.time_of_day} for loc in locs]
    series = _series_context(ctx)
    provider_key, simulated = "manual", False
    if manual:
        content = normalize_script(manual)
        ctx.log("Roteiro manual fornecido pelo usuário")
    else:
        system = prompts.system_for("story_writer", language=ctx.channel.language, region=ctx.channel.region, engine=_engine_dict(ctx))
        prompt = prompts.script_prompt(idea=idea_d, channel=_channel_dict(ctx), engine=_engine_dict(ctx), target_s=target,
                                       platform_hint=", ".join(ctx.channel.platforms or []), characters=char_d,
                                       locations=loc_d, series_context=series, variant=variant)
        task = {"type": "script", "idea": {**idea_d, "protagonist": (idea.data or {}).get("protagonist") if idea else None},
                "engine_type": ctx.engine.engine_type, "target_duration_s": target, "variant": variant or "",
                "characters": [{"name": c.name} for c in chars[:2]] if series else []}
        content, cand, simulated = llm_json(ctx.router, operation="write_script", system=system, prompt=prompt, task=task,
                                            max_tokens=12000, validate=normalize_script, agent="story_writer")
        provider_key = f"{cand.rec.key}:{cand.model_key}"
        if simulated:
            ctx.mark_simulated("llm")
        ctx.log("Roteiro gerado", provider=provider_key, scenes=len(content["scenes"]))
    script = ctx.db.get(Script, job.script_id) if job.script_id else None
    if script is None:
        script = Script(idea_id=job.idea_id, channel_id=job.channel_id, engine_id=job.engine_id, series_id=job.series_id,
                        episode_id=job.episode_id, title=content["title"], status="draft",
                        variant_group=(job.config or {}).get("variant_group"), variant_label=(job.config or {}).get("variant_label"))
        ctx.db.add(script)
        ctx.db.flush()
        job.script_id = script.id
    v = add_version(ctx.db, script, content, created_by="manual" if manual else "story_writer", provider=provider_key,
                    simulated=simulated, target_s=target)
    job.title = content["title"]
    if job.episode_id:
        ep = ctx.db.get(Episode, job.episode_id)
        ep.script_id = script.id
        ep.status = "in_production"
    return {"script_id": script.id, "version": v.version, "title": content["title"], "scenes": len(content["scenes"]),
            "estimated_duration_s": estimated_duration(content), "provider": provider_key, "simulated": simulated}


def script_editor(ctx: StepContext) -> dict:
    v = ctx.script_version()
    content = v.content
    target = v.target_duration_s
    limits = ctx.platform_limits()
    issues: list[str] = []
    est = estimated_duration(content)
    words = sum(len(s["narration"].split()) + sum(len(d["text"].split()) for d in s["dialogue"]) for s in content["scenes"])
    if est > limits["max"]:
        issues.append(f"Duração estimada {est:.0f}s excede o limite da plataforma ({limits['max']:.0f}s)")
    if est > target * 1.4:
        issues.append(f"Roteiro longo: {words} palavras (~{words / WORDS_PER_SECOND:.0f}s de fala) para alvo de {target}s")
    first = content["scenes"][0]
    if not (first["narration"] or first["dialogue"]):
        issues.append("Primeira cena sem gancho falado")
    if len(content["scenes"]) < 3:
        issues.append("Poucas cenas: ritmo pode ficar lento")
    long_lines = [d["text"] for s in content["scenes"] for d in s["dialogue"] if len(d["text"].split()) > 28]
    if long_lines:
        issues.append(f"{len(long_lines)} fala(s) longa(s) demais para vídeo curto")
    review = {"deterministic_issues": issues}
    if ctx.router.manual_llm():  # modo copiar e colar: só checagens automáticas (um único colar por vídeo)
        v.review = {**review, "llm": None, "note": "Revisão por LLM desativada no modo copiar e colar"}
        ctx.script().status = "approved"
        return {"issues": issues, "llm_review": None, "new_version": None, "estimated_duration_s": est, "manual_mode": True}
    system = prompts.system_for("script_editor", language=ctx.channel.language, region=ctx.channel.region, engine=_engine_dict(ctx))
    data, cand, simulated = llm_json(ctx.router, operation="review_script", system=system,
                                     prompt=prompts.review_prompt(content, target),
                                     task={"type": "script_review"}, max_tokens=12000)
    review.update({"llm": {k: data.get(k) for k in ("approved", "score", "issues", "suggestions")}, "provider": cand.rec.key})
    revised = data.get("revised") if isinstance(data, dict) else None
    new_version = None
    if revised and not simulated:
        try:
            rc = normalize_script(revised)
            if estimated_duration(rc) <= limits["max"]:
                new_version = add_version(ctx.db, ctx.script(), rc, created_by="script_editor", provider=cand.rec.key,
                                          notes="Revisão automática", review=review, target_s=target).version
                ctx.log("Nova versão revisada criada", version=new_version)
        except ValueError as e:
            ctx.log("Revisão descartada (formato inválido)", error=str(e))
    if not new_version:
        v.review = review
    if est > limits["max"] and not new_version:
        ctx.job.config = {**(ctx.job.config or {}), "force_review": True,
                          "review_reasons": [*(ctx.job.config or {}).get("review_reasons", []), "Roteiro excede duração máxima"]}
    ctx.script().status = "approved"
    return {"issues": issues, "llm_review": review.get("llm"), "new_version": new_version, "estimated_duration_s": est}


def fact_checker(ctx: StepContext) -> dict:
    if not (ctx.engine.config or {}).get("requires_fact_check"):
        return {"skipped": True, "reason": "Motor não exige verificação de fatos"}
    v = ctx.script_version()
    claims = v.content.get("fact_claims") or [{"claim": s["narration"], "source": None} for s in v.content["scenes"] if s["narration"]]
    if ctx.router.manual_llm() or v.is_simulated is False and any(c.get("sources") or c.get("source") for c in claims):
        # Verificação automática: as fontes indicadas no roteiro são abertas; só vai para revisão o que não se confirmar.
        from app.services.factcheck import check_claims

        results = check_claims(claims)
        bad = [r for r in results if not r["verified"]]
        if bad or not results:
            reason = (f"{len(bad)} fato(s) sem fonte acessível: " + "; ".join((r["claim"] or "")[:60] for r in bad[:3])) if bad \
                else "Roteiro de curiosidades sem fatos listados para verificar"
            ctx.job.config = {**(ctx.job.config or {}), "force_review": True,
                              "review_reasons": [*(ctx.job.config or {}).get("review_reasons", []), reason]}
        v.content = {**v.content, "fact_check": results}
        ctx.log("Fontes verificadas automaticamente", total=len(results), sem_confirmacao=len(bad))
        return {"claims": len(results), "unverified": len(bad), "method": "automatic_source_check"}
    data, cand, simulated = llm_json(ctx.router, operation="fact_check", system=prompts.system_for("fact_checker"),
                                     prompt=prompts.fact_check_prompt(claims), task={"type": "fact_check", "claims": claims},
                                     max_tokens=6000)
    from app.services.factcheck import check_claims

    results = check_claims(data.get("claims", [])) if not simulated else data.get("claims", [])
    unverified = [c for c in results if not c.get("verified")]
    if simulated or unverified:
        reasons = ["Verificação de fatos simulada: requer revisão humana"] if simulated else \
                  [f"{len(unverified)} afirmação(ões) sem verificação confiável"]
        ctx.job.config = {**(ctx.job.config or {}), "force_review": True,
                          "review_reasons": [*(ctx.job.config or {}).get("review_reasons", []), *reasons]}
    v.content = {**v.content, "fact_check": results}
    return {"claims": len(results), "unverified": len(unverified), "simulated": simulated, "provider": cand.rec.key}
