from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import editor, viewer
from app.api.utils import apply_updates, get_or_404, page, serialize
from app.core.config import settings
from app.core.db import get_db
from app.core.errors import ValidationFailed
from app.media.animation.backgrounds import background_png
from app.media.animation.preview import character_sheet_png
from app.models import (
    Asset,
    Character,
    CharacterAppearance,
    CharacterAsset,
    CharacterRelationship,
    Episode,
    Location,
    ProductionJob,
    Script,
    ScriptVersion,
    Series,
    Template,
    Universe,
    User,
    Voice,
)
from app.pipeline.agents.design import visual_spec_from_appearance
from app.pipeline.orchestrator import create_production
from app.providers.router import ProviderRouter
from app.schemas import (
    CharacterIn,
    EpisodeIn,
    LocationIn,
    RelationshipIn,
    ScriptVersionIn,
    SeriesIn,
    TemplateIn,
    UniverseIn,
    VoiceIn,
    VoiceTestIn,
)
from app.services.assets import asset_public, store_asset
from app.services.common import audit
from app.services.scripts import add_version, normalize_script

router = APIRouter(tags=["content"])


# ---------------------------------------------------------------- roteiros
@router.get("/scripts")
def list_scripts(channel_id: int | None = None, status: str | None = None, q: str | None = None, limit: int = 50, offset: int = 0,
                 db: Session = Depends(get_db), _: User = Depends(viewer)):
    query = select(Script)
    if channel_id:
        query = query.where(Script.channel_id == channel_id)
    if status:
        query = query.where(Script.status == status)
    if q:
        query = query.where(Script.title.ilike(f"%{q}%"))

    def mapper(s: Script) -> dict:
        v = db.scalar(select(ScriptVersion).where(ScriptVersion.script_id == s.id, ScriptVersion.version == s.current_version))
        job = db.scalar(select(ProductionJob.id).where(ProductionJob.script_id == s.id).order_by(ProductionJob.id.desc()).limit(1))
        return serialize(s, extra={"synopsis": v.synopsis if v else "", "scenes": len((v.content or {}).get("scenes", [])) if v else 0,
                                   "is_simulated": v.is_simulated if v else False, "production_id": job,
                                   "target_duration_s": v.target_duration_s if v else None})

    return page(db, query.order_by(Script.updated_at.desc()), limit=limit, offset=offset, mapper=mapper)


@router.get("/scripts/{sid}")
def get_script(sid: int, db: Session = Depends(get_db), _: User = Depends(viewer)):
    s = get_or_404(db, Script, sid, "Roteiro")
    versions = db.scalars(select(ScriptVersion).where(ScriptVersion.script_id == sid).order_by(ScriptVersion.version.desc())).all()
    jobs = db.scalars(select(ProductionJob.id).where(ProductionJob.script_id == sid)).all()
    return serialize(s, extra={"versions": [serialize(v) for v in versions], "production_ids": jobs})


@router.post("/scripts/{sid}/versions", status_code=201)
def new_script_version(sid: int, body: ScriptVersionIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    s = get_or_404(db, Script, sid, "Roteiro")
    try:
        content = normalize_script(body.content)
    except ValueError as e:
        raise ValidationFailed(f"Roteiro inválido: {e}") from e
    v = add_version(db, s, content, created_by=f"user:{user.id}", notes=body.notes)
    audit(db, "script.version", user_id=user.id, entity_type="script", entity_id=sid, data={"version": v.version})
    db.commit()
    return serialize(v)


@router.post("/scripts/{sid}/versions/{version}/restore")
def restore_version(sid: int, version: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    s = get_or_404(db, Script, sid, "Roteiro")
    v = db.scalar(select(ScriptVersion).where(ScriptVersion.script_id == sid, ScriptVersion.version == version))
    if not v:
        raise HTTPException(404, "Versão não encontrada")
    nv = add_version(db, s, v.content, created_by=f"user:{user.id}", notes=f"Restaurada da v{version}")
    db.commit()
    return serialize(nv)


# ---------------------------------------------------------------- universos / séries / episódios
@router.get("/universes")
def list_universes(db: Session = Depends(get_db), _: User = Depends(viewer)):
    out = []
    for u in db.scalars(select(Universe).order_by(Universe.name)):
        out.append(serialize(u, extra={
            "characters": db.scalar(select(func.count()).select_from(Character).where(Character.universe_id == u.id)),
            "series": db.scalar(select(func.count()).select_from(Series).where(Series.universe_id == u.id))}))
    return out


@router.post("/universes", status_code=201)
def create_universe(body: UniverseIn, db: Session = Depends(get_db), _: User = Depends(editor)):
    u = Universe(**body.model_dump())
    db.add(u)
    db.commit()
    return serialize(u)


@router.patch("/universes/{uid}")
def update_universe(uid: int, body: UniverseIn, db: Session = Depends(get_db), _: User = Depends(editor)):
    u = apply_updates(get_or_404(db, Universe, uid, "Universo"), body.model_dump(exclude_unset=True))
    db.commit()
    return serialize(u)


@router.delete("/universes/{uid}", status_code=204)
def delete_universe(uid: int, db: Session = Depends(get_db), _: User = Depends(editor)):
    db.delete(get_or_404(db, Universe, uid, "Universo"))
    db.commit()


@router.get("/series")
def list_series(channel_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(viewer)):
    q = select(Series)
    if channel_id:
        q = q.where(Series.channel_id == channel_id)
    out = []
    for s in db.scalars(q.order_by(Series.updated_at.desc())):
        n = db.scalar(select(func.count()).select_from(Episode).where(Episode.series_id == s.id))
        out.append(serialize(s, extra={"episodes": n}))
    return out


@router.post("/series", status_code=201)
def create_series(body: SeriesIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    s = Series(**body.model_dump())
    db.add(s)
    audit(db, "series.create", user_id=user.id, entity_type="series")
    db.commit()
    return serialize(s)


@router.get("/series/{sid}")
def get_series(sid: int, db: Session = Depends(get_db), _: User = Depends(viewer)):
    s = get_or_404(db, Series, sid, "Série")
    eps = db.scalars(select(Episode).where(Episode.series_id == sid).order_by(Episode.number)).all()
    chars = []
    if s.universe_id:
        chars = db.scalars(select(Character).where(Character.universe_id == s.universe_id)).all()
    ep_ids = [e.id for e in eps]
    appear = db.scalars(select(CharacterAppearance).where(CharacterAppearance.episode_id.in_(ep_ids))).all() if ep_ids else []
    extra_ids = {a.character_id for a in appear} - {c.id for c in chars}
    chars = list(chars) + list(db.scalars(select(Character).where(Character.id.in_(extra_ids))).all() if extra_ids else [])
    rels = db.scalars(select(CharacterRelationship).where(CharacterRelationship.character_id.in_([c.id for c in chars]))).all() if chars else []
    return serialize(s, extra={"episodes": [serialize(e) for e in eps], "characters": [serialize(c) for c in chars],
                               "relationships": [serialize(r) for r in rels],
                               "appearances": [{"character_id": a.character_id, "episode_id": a.episode_id, "scenes": a.scene_count} for a in appear],
                               "universe": serialize(db.get(Universe, s.universe_id)) if s.universe_id else None})


@router.patch("/series/{sid}")
def update_series(sid: int, body: SeriesIn, db: Session = Depends(get_db), _: User = Depends(editor)):
    s = apply_updates(get_or_404(db, Series, sid, "Série"), body.model_dump(exclude_unset=True))
    db.commit()
    return serialize(s)


@router.delete("/series/{sid}", status_code=204)
def delete_series(sid: int, db: Session = Depends(get_db), _: User = Depends(editor)):
    db.delete(get_or_404(db, Series, sid, "Série"))
    db.commit()


@router.post("/series/{sid}/episodes", status_code=201)
def create_episode(sid: int, body: EpisodeIn, db: Session = Depends(get_db), _: User = Depends(editor)):
    get_or_404(db, Series, sid, "Série")
    n = body.number or (db.scalar(select(func.max(Episode.number)).where(Episode.series_id == sid)) or 0) + 1
    if db.scalar(select(Episode.id).where(Episode.series_id == sid, Episode.number == n)):
        raise HTTPException(409, f"Episódio {n} já existe")
    e = Episode(series_id=sid, number=n, title=body.title, synopsis=body.synopsis, standalone_friendly=body.standalone_friendly)
    db.add(e)
    db.commit()
    return serialize(e)


@router.patch("/episodes/{eid}")
def update_episode(eid: int, body: EpisodeIn, db: Session = Depends(get_db), _: User = Depends(editor)):
    e = apply_updates(get_or_404(db, Episode, eid, "Episódio"), body.model_dump(exclude_unset=True, exclude={"number"}))
    db.commit()
    return serialize(e)


@router.post("/episodes/{eid}/produce")
def produce_episode(eid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    e = get_or_404(db, Episode, eid, "Episódio")
    s = db.get(Series, e.series_id)
    if not s.channel_id or not s.engine_id:
        raise HTTPException(422, "Defina canal e motor da série antes de produzir")
    job = create_production(db, channel_id=s.channel_id, engine_id=s.engine_id, series_id=s.id, episode_id=e.id,
                            title=e.title, user_id=user.id, visual_style=s.visual_style)
    return {"production_id": job.id}


# ---------------------------------------------------------------- personagens
def character_view(db: Session, c: Character, full: bool = False) -> dict:
    assets = db.scalars(select(CharacterAsset).where(CharacterAsset.character_id == c.id)).all()
    extra = {"assets": [serialize(a, extra={"asset": asset_public(db.get(Asset, a.asset_id))}) for a in assets],
             "voice": serialize(db.get(Voice, c.voice_id)) if c.voice_id else None}
    if full:
        rels = db.scalars(select(CharacterRelationship).where(or_(CharacterRelationship.character_id == c.id,
                                                                  CharacterRelationship.other_character_id == c.id))).all()
        apps = db.scalars(select(CharacterAppearance).where(CharacterAppearance.character_id == c.id)
                          .order_by(CharacterAppearance.created_at.desc()).limit(100)).all()
        extra["relationships"] = [serialize(r, extra={"other": {"id": o.id, "name": o.name}}) for r in rels
                                  if (o := db.get(Character, r.other_character_id if r.character_id == c.id else r.character_id))]
        extra["appearances"] = [serialize(a, extra={"title": (j.title if (j := db.get(ProductionJob, a.production_job_id)) else None)}) for a in apps]
    return serialize(c, extra=extra)


@router.get("/characters")
def list_characters(channel_id: int | None = None, universe_id: int | None = None, q: str | None = None, role_type: str | None = None,
                    limit: int = 100, offset: int = 0, db: Session = Depends(get_db), _: User = Depends(viewer)):
    query = select(Character)
    if channel_id:
        query = query.where(or_(Character.channel_id == channel_id, Character.is_shared.is_(True)))
    if universe_id:
        query = query.where(Character.universe_id == universe_id)
    if role_type:
        query = query.where(Character.role_type == role_type)
    if q:
        query = query.where(Character.name.ilike(f"%{q}%"))
    return page(db, query.order_by(Character.appearance_count.desc(), Character.name), limit=limit, offset=offset,
                mapper=lambda c: character_view(db, c))


def _refresh_preview(db: Session, c: Character) -> None:
    for ca in db.scalars(select(CharacterAsset).where(CharacterAsset.character_id == c.id, CharacterAsset.kind == "preview")):
        db.delete(ca)
    png = character_sheet_png(c.visual_spec, c.name)
    a = store_asset(db, kind="image", name=f"{c.name}_sheet.png", data=png, mime="image/png", origin="procedural",
                    license="internal_generated", key_prefix=f"characters/{c.id}", is_reusable=True, width=900, height=900)
    db.add(CharacterAsset(character_id=c.id, asset_id=a.id, kind="preview", label="Folha de referência", is_primary=True))


@router.post("/characters", status_code=201)
def create_character(body: CharacterIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    data = body.model_dump()
    if not data["visual_spec"].get("style"):
        data["visual_spec"] = {**visual_spec_from_appearance(body.name, data["visual_spec"], body.art_style), **data["visual_spec"]}
    c = Character(**data)
    db.add(c)
    db.flush()
    _refresh_preview(db, c)
    audit(db, "character.create", user_id=user.id, entity_type="character", entity_id=c.id)
    db.commit()
    return character_view(db, c, True)


@router.get("/characters/{cid}")
def get_character(cid: int, db: Session = Depends(get_db), _: User = Depends(viewer)):
    return character_view(db, get_or_404(db, Character, cid, "Personagem"), True)


@router.patch("/characters/{cid}")
def update_character(cid: int, body: CharacterIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    c = get_or_404(db, Character, cid, "Personagem")
    data = body.model_dump(exclude_unset=True)
    visual_changed = "visual_spec" in data and data["visual_spec"] != c.visual_spec
    if "visual_spec" in data:
        data["visual_spec"] = {**(c.visual_spec or {}), **data["visual_spec"]}
    apply_updates(c, data)
    if visual_changed:
        _refresh_preview(db, c)
    audit(db, "character.update", user_id=user.id, entity_type="character", entity_id=cid, data={"visual_changed": visual_changed})
    db.commit()
    return character_view(db, c, True)


@router.delete("/characters/{cid}", status_code=204)
def delete_character(cid: int, db: Session = Depends(get_db), user: User = Depends(editor)):
    c = get_or_404(db, Character, cid, "Personagem")
    audit(db, "character.delete", user_id=user.id, entity_type="character", entity_id=cid, data={"name": c.name})
    db.delete(c)
    db.commit()


@router.post("/characters/{cid}/references", status_code=201)
async def upload_reference(cid: int, file: UploadFile = File(...), db: Session = Depends(get_db), _: User = Depends(editor)):
    c = get_or_404(db, Character, cid, "Personagem")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(422, "Envie uma imagem")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "Imagem maior que 15 MB")
    a = store_asset(db, kind="image", name=file.filename or "ref.png", data=data, mime=file.content_type, origin="uploaded",
                    license="user_owned", key_prefix=f"characters/{c.id}", is_reusable=True, tags=["character", "reference"])
    db.add(CharacterAsset(character_id=c.id, asset_id=a.id, kind="reference", label=file.filename or ""))
    db.commit()
    return character_view(db, c, True)


@router.post("/characters/{cid}/relationships", status_code=201)
def add_relationship(cid: int, body: RelationshipIn, db: Session = Depends(get_db), _: User = Depends(editor)):
    get_or_404(db, Character, cid, "Personagem")
    get_or_404(db, Character, body.other_character_id, "Personagem")
    if cid == body.other_character_id:
        raise HTTPException(422, "Relação consigo mesmo")
    r = db.scalar(select(CharacterRelationship).where(CharacterRelationship.character_id == cid,
                                                      CharacterRelationship.other_character_id == body.other_character_id))
    r = r or CharacterRelationship(character_id=cid, other_character_id=body.other_character_id, relation_type=body.relation_type)
    apply_updates(r, body.model_dump())
    db.add(r)
    db.commit()
    return serialize(r)


@router.delete("/relationships/{rid}", status_code=204)
def delete_relationship(rid: int, db: Session = Depends(get_db), _: User = Depends(editor)):
    db.delete(get_or_404(db, CharacterRelationship, rid, "Relação"))
    db.commit()


# ---------------------------------------------------------------- cenários
@router.get("/locations")
def list_locations(channel_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(viewer)):
    q = select(Location)
    if channel_id:
        q = q.where(Location.channel_id == channel_id)
    return [serialize(loc, extra={"background": asset_public(db.get(Asset, loc.background_asset_id)) if loc.background_asset_id else None})
            for loc in db.scalars(q.order_by(Location.reuse_count.desc()))]


def _location_bg(db: Session, loc: Location) -> None:
    png = background_png(loc.setting_type, loc.time_of_day, 1253, 2227, f"loc{loc.id}", loc.palette or None)
    a = store_asset(db, kind="image", name=f"bg_{loc.id}.png", data=png, mime="image/png", origin="procedural", license="internal_generated",
                    channel_id=loc.channel_id, is_reusable=True, tags=["background", "location"], width=1253, height=2227,
                    key_prefix=f"locations/{loc.id}")
    loc.background_asset_id = a.id


@router.post("/locations", status_code=201)
def create_location(body: LocationIn, db: Session = Depends(get_db), _: User = Depends(editor)):
    loc = Location(**body.model_dump())
    db.add(loc)
    db.flush()
    _location_bg(db, loc)
    db.commit()
    return serialize(loc, extra={"background": asset_public(db.get(Asset, loc.background_asset_id))})


@router.patch("/locations/{lid}")
def update_location(lid: int, body: LocationIn, db: Session = Depends(get_db), _: User = Depends(editor)):
    loc = get_or_404(db, Location, lid, "Cenário")
    data = body.model_dump(exclude_unset=True)
    regen = any(k in data and data[k] != getattr(loc, k) for k in ("setting_type", "time_of_day", "palette"))
    apply_updates(loc, data)
    if regen:
        _location_bg(db, loc)
    db.commit()
    return serialize(loc, extra={"background": asset_public(db.get(Asset, loc.background_asset_id)) if loc.background_asset_id else None})


@router.delete("/locations/{lid}", status_code=204)
def delete_location(lid: int, db: Session = Depends(get_db), _: User = Depends(editor)):
    db.delete(get_or_404(db, Location, lid, "Cenário"))
    db.commit()


# ---------------------------------------------------------------- vozes
@router.get("/voices")
def list_voices(db: Session = Depends(get_db), _: User = Depends(viewer)):
    router_ = ProviderRouter(db)
    available = {c.rec.key for c in router_.candidates("tts", allow_simulated=False)}
    out = []
    for v in db.scalars(select(Voice).order_by(Voice.provider_key, Voice.name)):
        used = db.scalars(select(Character.name).where(Character.voice_id == v.id)).all()
        out.append(serialize(v, extra={"provider_available": v.provider_key in available, "characters": used,
                                       "sample": asset_public(db.get(Asset, v.sample_asset_id)) if v.sample_asset_id else None}))
    return out


@router.post("/voices", status_code=201)
def create_voice(body: VoiceIn, db: Session = Depends(get_db), user: User = Depends(editor)):
    v = Voice(**body.model_dump())
    db.add(v)
    audit(db, "voice.create", user_id=user.id, entity_type="voice")
    db.commit()
    return serialize(v)


@router.patch("/voices/{vid}")
def update_voice(vid: int, body: VoiceIn, db: Session = Depends(get_db), _: User = Depends(editor)):
    v = apply_updates(get_or_404(db, Voice, vid, "Voz"), body.model_dump(exclude_unset=True))
    db.commit()
    return serialize(v)


@router.delete("/voices/{vid}", status_code=204)
def delete_voice(vid: int, db: Session = Depends(get_db), _: User = Depends(editor)):
    db.delete(get_or_404(db, Voice, vid, "Voz"))
    db.commit()


@router.post("/voices/{vid}/test")
def test_voice(vid: int, body: VoiceTestIn, db: Session = Depends(get_db), _: User = Depends(editor)):
    from app.media import audio as A

    v = get_or_404(db, Voice, vid, "Voz")
    r = ProviderRouter(db)
    vs = v.settings or {}
    res, cand = r.call("tts", "voice_test",
                       lambda p, m: p.synthesize(text=body.text, voice_id=v.provider_voice_id if p.key == v.provider_key else
                                                 (p.config.get("default_voices", {}).get(v.gender) or ""), language=v.language,
                                                 speed=float(vs.get("speed", 1.0)), pitch=float(vs.get("pitch", 0)), emotion=body.emotion,
                                                 settings=vs, model=m),
                       lambda p, m: p.estimate_cost(chars=len(body.text), model=m), preferred=v.provider_key)
    wd = Path(settings.work_dir) / "voice_tests"
    wd.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256(res.data).hexdigest()[:12]
    raw = wd / f"{h}{'.mp3' if res.mime == 'audio/mpeg' else '.wav'}"
    raw.write_bytes(res.data)
    wav = A.normalize_to_wav(raw, wd / f"{h}_n.wav")
    a = store_asset(db, kind="audio", name=f"voz_{v.id}_amostra.wav", path=wav, mime="audio/wav", origin="generated",
                    license="internal_generated" if cand.rec.key == "espeak" else "provider_commercial", provider_key=cand.rec.key,
                    key_prefix=f"voices/{v.id}", prompt=body.text)
    v.sample_asset_id = a.id
    db.commit()
    return {"asset": asset_public(a), "provider": cand.rec.key, "fallback": cand.rec.key != v.provider_key}


@router.get("/voices/catalog/{provider_key}")
def voice_catalog(provider_key: str, db: Session = Depends(get_db), _: User = Depends(editor)):
    from app.models import ModelProvider
    from app.providers.registry import build_provider

    rec = db.scalar(select(ModelProvider).where(ModelProvider.key == provider_key, ModelProvider.kind == "tts"))
    if not rec:
        raise HTTPException(404, "Provedor TTS não encontrado")
    try:
        return build_provider(db, rec).list_voices()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(424, f"Não foi possível listar vozes: {getattr(e, 'message', str(e))}") from e


# ---------------------------------------------------------------- templates de edição
@router.get("/templates")
def list_templates(db: Session = Depends(get_db), _: User = Depends(viewer)):
    from app.pipeline.context import DEFAULT_TEMPLATE

    return {"defaults": DEFAULT_TEMPLATE, "items": [serialize(t) for t in db.scalars(select(Template).order_by(Template.id))]}


@router.post("/templates", status_code=201)
def create_template(body: TemplateIn, db: Session = Depends(get_db), _: User = Depends(editor)):
    if body.is_default:
        for t in db.scalars(select(Template).where(Template.is_default.is_(True))):
            t.is_default = False
    t = Template(**body.model_dump())
    db.add(t)
    db.commit()
    return serialize(t)


@router.patch("/templates/{tid}")
def update_template(tid: int, body: TemplateIn, db: Session = Depends(get_db), _: User = Depends(editor)):
    t = get_or_404(db, Template, tid, "Template")
    data = body.model_dump(exclude_unset=True)
    if data.get("is_default"):
        for o in db.scalars(select(Template).where(Template.is_default.is_(True), Template.id != tid)):
            o.is_default = False
    apply_updates(t, data)
    db.commit()
    return serialize(t)


@router.delete("/templates/{tid}", status_code=204)
def delete_template(tid: int, db: Session = Depends(get_db), _: User = Depends(editor)):
    db.delete(get_or_404(db, Template, tid, "Template"))
    db.commit()
