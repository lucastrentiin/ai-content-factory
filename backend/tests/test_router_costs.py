"""Roteamento de provedores: fallback, circuit breaker, limites de custo e registro de uso."""
import pytest
from sqlalchemy import select

from app.core.errors import BudgetExceeded, ProviderError
from app.models import ApiUsage, CostLimit, ModelProvider, ProviderModel
from app.providers.base import LLMProvider, LLMResult, Usage
from app.providers.registry import ADAPTERS
from app.providers.router import ProviderRouter, parse_json
from app.services.costs import CallContext


class FlakyLLM(LLMProvider):
    adapter = "test_flaky"
    calls = 0

    def generate(self, **kw):
        FlakyLLM.calls += 1
        raise ProviderError("falha simulada de teste", retryable=True)

    def estimate_cost(self, **kw):
        return 0.01


class PaidLLM(LLMProvider):
    adapter = "test_paid"

    def generate(self, **kw):
        return LLMResult(text='{"ok": true}', model="paid", usage=Usage(units={"input_tokens": 10}, cost_usd=0.5))

    def estimate_cost(self, **kw):
        return 0.5


@pytest.fixture()
def fake_providers(db):
    ADAPTERS["test_flaky"], ADAPTERS["test_paid"] = FlakyLLM, PaidLLM
    recs = [ModelProvider(key="t-flaky", name="flaky", kind="llm", adapter="test_flaky", priority=1),
            ModelProvider(key="t-paid", name="paid", kind="llm", adapter="test_paid", priority=2)]
    db.add_all(recs)
    db.commit()
    yield recs
    for r in recs:
        db.delete(db.get(ModelProvider, r.id))
    db.commit()


def test_fallback_and_circuit_breaker(db, fake_providers):
    r = ProviderRouter(db, CallContext(strategy="cost"))
    for _ in range(3):
        res, cand = r.call("llm", "t", lambda p, m: p.generate(), lambda p, m: p.estimate_cost(), preferred="t-flaky")
        assert cand.rec.key == "t-paid"
    flaky = db.scalar(select(ModelProvider).where(ModelProvider.key == "t-flaky"))
    assert flaky.circuit_open_until is not None  # 3 falhas seguidas abrem o circuito
    before = FlakyLLM.calls
    r.call("llm", "t", lambda p, m: p.generate(), lambda p, m: p.estimate_cost(), preferred="t-flaky")
    assert FlakyLLM.calls == before  # provedor com circuito aberto não é chamado
    fails = db.scalars(select(ApiUsage).where(ApiUsage.provider_key == "t-flaky", ApiUsage.success.is_(False))).all()
    assert len(fails) >= 3


def test_budget_blocks_paid_and_falls_back_to_free(db, fake_providers):
    lim = CostLimit(scope="global", period="daily", limit_usd=0.3, action="block")
    db.add(lim)
    db.commit()
    try:
        r = ProviderRouter(db, CallContext())
        res, cand = r.call("llm", "t", lambda p, m: p.generate(system="s", prompt="p", task={"type": "metadata"}),
                           lambda p, m: p.estimate_cost(prompt_chars=1, max_tokens=1), preferred="t-paid")
        assert cand.rec.is_simulated  # pago bloqueado → simulado gratuito
        with pytest.raises(BudgetExceeded):
            r.call("llm", "t", lambda p, m: p.generate(), lambda p, m: p.estimate_cost(), allow_simulated=False, preferred="t-paid")
    finally:
        db.delete(db.get(CostLimit, lim.id))
        db.commit()


def test_parse_json_tolerant():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Claro! {"a": [1,2]} fim') == {"a": [1, 2]}
    with pytest.raises(ProviderError):
        parse_json("sem json")


def test_seeded_pricing_is_editable(db):
    m = db.scalar(select(ProviderModel).where(ProviderModel.model_key == "claude-opus-5-5"))
    assert m.pricing["input_per_1m_tokens"] > 0 and m.is_default
