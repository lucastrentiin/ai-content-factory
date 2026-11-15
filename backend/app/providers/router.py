"""Roteador de provedores: escolhe por estratégia (qualidade/custo/velocidade), aplica limites de custo,
circuit breaker, fallback automático entre provedores e registra todo uso em `api_usage`."""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BudgetExceeded, MissingCredentials, ProviderError, ProviderUnavailable
from app.core.logging import get_logger
from app.models import ModelProvider, ProviderModel
from app.providers.base import BaseProvider
from app.providers.registry import build_provider
from app.services.common import get_setting
from app.services.costs import CallContext, check_budget, record_usage

log = get_logger(__name__)
T = TypeVar("T")
CIRCUIT_THRESHOLD = 3
CIRCUIT_COOLDOWN = timedelta(minutes=5)


class Candidate:
    def __init__(self, rec: ModelProvider, provider: BaseProvider, model: ProviderModel | None):
        self.rec, self.provider, self.model = rec, provider, model

    @property
    def model_key(self) -> str:
        return self.model.model_key if self.model else self.provider.model()


class ProviderRouter:
    def __init__(self, db: Session, ctx: CallContext | None = None):
        self.db = db
        self.ctx = ctx or CallContext()

    def candidates(self, kind: str, *, preferred: str | None = None, allow_simulated: bool | None = None) -> list[Candidate]:
        if allow_simulated is None:
            allow_simulated = bool(get_setting(self.db, "providers").get("allow_simulated", True))
        recs = self.db.scalars(select(ModelProvider).where(ModelProvider.kind == kind, ModelProvider.is_enabled.is_(True))).all()
        now = datetime.now(UTC)
        out: list[Candidate] = []
        for rec in recs:
            if rec.is_simulated and not allow_simulated:
                continue
            if rec.circuit_open_until and rec.circuit_open_until > now:
                continue
            try:
                prov = build_provider(self.db, rec)
            except ValueError:
                continue
            if not prov.status().ok:
                continue
            models = self.db.scalars(select(ProviderModel).where(ProviderModel.provider_id == rec.id, ProviderModel.is_enabled.is_(True))).all()
            model = next((m for m in models if m.is_default), models[0] if models else None)
            out.append(Candidate(rec, prov, model))
        strategy = self.ctx.strategy

        def sort_key(c: Candidate) -> tuple:
            q = c.model.quality_score if c.model else 5
            sp = c.model.speed_score if c.model else 5
            price = sum(float(v) for v in (c.model.pricing if c.model else {}).values() if isinstance(v, (int, float)))
            pref = 0 if preferred and c.rec.key == preferred else 1
            base = {"quality": -q, "cost": price, "speed": -sp}.get(strategy, -q + price * 0.5)
            return (pref, 1 if c.rec.is_simulated else 0, base, c.rec.priority)

        return sorted(out, key=sort_key)

    def call(self, kind: str, operation: str, fn: Callable[[BaseProvider, str], T],
             estimate: Callable[[BaseProvider, str], float], *, preferred: str | None = None,
             allow_simulated: bool | None = None) -> tuple[T, Candidate]:
        cands = self.candidates(kind, preferred=preferred, allow_simulated=allow_simulated)
        if not cands:
            raise ProviderUnavailable(f"Nenhum provedor '{kind}' configurado e disponível. Configure em Configurações → Provedores.")
        errors: list[str] = []
        budget_error: BudgetExceeded | None = None
        for c in cands:
            est = 0.0
            try:
                est = float(estimate(c.provider, c.model_key))
                check_budget(self.db, self.ctx, est)
            except BudgetExceeded as e:
                budget_error = e
                errors.append(f"{c.rec.key}: {e.message}")
                continue  # tenta provedores gratuitos/locais
            t0 = time.time()
            try:
                result = fn(c.provider, c.model_key)
            except MissingCredentials as e:
                errors.append(f"{c.rec.key}: {e.message}")
                continue
            except ProviderError as e:
                ms = int((time.time() - t0) * 1000)
                record_usage(self.db, self.ctx, provider_key=c.rec.key, model_key=c.model_key, kind=kind, operation=operation,
                             units={}, est_cost=0, duration_ms=ms, success=False, simulated=c.rec.is_simulated, error=e.message[:500])
                self._failure(c.rec, e.message)
                errors.append(f"{c.rec.key}: {e.message}")
                log.warning("provedor falhou, tentando próximo", extra={"provider": c.rec.key, "error": e.message})
                continue
            ms = int((time.time() - t0) * 1000)
            usage = getattr(result, "usage", None)
            record_usage(self.db, self.ctx, provider_key=c.rec.key, model_key=getattr(result, "model", c.model_key), kind=kind,
                         operation=operation, units=getattr(usage, "units", {}) or {},
                         est_cost=getattr(usage, "cost_usd", est) if usage else est,
                         actual_cost=getattr(usage, "actual_cost_usd", None) if usage else None,
                         duration_ms=ms, simulated=c.rec.is_simulated)
            if c.rec.consecutive_failures:
                c.rec.consecutive_failures = 0
                c.rec.circuit_open_until = None
            return result, c
        if budget_error and all("Limite de custo" in e for e in errors):
            raise budget_error
        raise ProviderError(f"Todos os provedores '{kind}' falharam: " + " | ".join(errors)[:1500], retryable=True)

    def _failure(self, rec: ModelProvider, msg: str) -> None:
        rec.consecutive_failures = (rec.consecutive_failures or 0) + 1
        rec.status_detail = msg[:500]
        if rec.consecutive_failures >= CIRCUIT_THRESHOLD:
            rec.circuit_open_until = datetime.now(UTC) + CIRCUIT_COOLDOWN
            rec.status = "error"

    def has_real(self, kind: str) -> bool:
        return any(not c.rec.is_simulated for c in self.candidates(kind, allow_simulated=False))


def parse_json(text: str) -> Any:
    """Extrai JSON de respostas de LLM (tolerante a cercas de código e texto ao redor)."""
    import json
    import re

    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        s, e = t.find(open_c), t.rfind(close_c)
        if s != -1 and e > s:
            try:
                return json.loads(t[s:e + 1])
            except json.JSONDecodeError:
                continue
    raise ProviderError("Resposta do LLM não contém JSON válido", retryable=True)


def llm_json(router: ProviderRouter, *, operation: str, system: str, prompt: str, task: dict, max_tokens: int = 8000,
             preferred: str | None = None, validate: Callable[[Any], Any] | None = None, attempts: int = 2) -> tuple[Any, Candidate, bool]:
    """Chama o LLM esperando JSON; valida e repete em caso de saída inválida. Retorna (dados, candidato, simulado)."""
    last: Exception | None = None
    for _ in range(attempts):
        res, cand = router.call(
            "llm", operation,
            lambda p, m: p.generate(system=system, prompt=prompt, model=m, max_tokens=max_tokens, json_mode=True, task=task),
            lambda p, m: p.estimate_cost(prompt_chars=len(system) + len(prompt), max_tokens=max_tokens, model=m),
            preferred=preferred,
        )
        try:
            data = parse_json(res.text)
            if validate:
                data = validate(data)
            return data, cand, bool(getattr(res, "simulated", False) or cand.rec.is_simulated)
        except (ProviderError, ValueError, KeyError, TypeError) as e:
            last = e
            prompt += "\n\nATENÇÃO: sua resposta anterior não era um JSON válido no formato pedido. Responda apenas o JSON."
    raise ProviderError(f"Saída inválida do LLM: {last}", retryable=True)
