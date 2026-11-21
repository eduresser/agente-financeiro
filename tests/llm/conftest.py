import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from dotenv import dotenv_values
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver

from banco_agil.config import Settings
from banco_agil.exchange import ProviderUnavailable, Quote
from banco_agil.graph.builder import build_graph
from banco_agil.guardrails import LocalGuardrail, other_customers_patterns
from banco_agil.guardrails.judge import ModelJudge
from banco_agil.llm import build_chat_model, build_judge_model
from banco_agil.seed import bootstrap
from banco_agil.service import ChatService
from banco_agil.storage import CustomerRepository, LimitRequestRepository, ScoreLimitRepository

NOW = datetime(2026, 11, 16, 12, 0, 0)
FAKE_MODEL = "test/chat-model"
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
SETTING_NAMES = [
    "CHAT_MODEL",
    "CHAT_MODEL_API_KEY",
    "CHAT_MODEL_BASE_URL",
    "JUDGE_CHAT_MODEL",
    "JUDGE_CHAT_MODEL_API_KEY",
    "JUDGE_CHAT_MODEL_BASE_URL",
]
FAIL_FAST = {"request_timeout": 30, "max_retries": 1}
RATES = {"USD": ("Dólar Americano", "5.43"), "EUR": ("Euro", "6.01")}


class FixedExchange:
    def get_rate(self, currency: str | None, target: str | None = None) -> Quote:
        code = (currency or "USD").strip().upper()
        code = {"DÓLAR": "USD", "DOLAR": "USD", "EURO": "EUR"}.get(code, code)
        if code not in RATES:
            raise ProviderUnavailable("unsupported in this scenario")
        name, rate = RATES[code]
        return Quote(code, name, Decimal(rate), NOW)


class DownExchange:
    def get_rate(self, currency: str | None, target: str | None = None) -> Quote:
        raise ProviderUnavailable("simulated outage")


@dataclass
class Run:
    transcript: str
    replies: list[str]
    failed: bool
    ended: bool
    data_dir: Path

    @property
    def customers(self) -> CustomerRepository:
        return CustomerRepository(self.data_dir / "clientes.csv")

    def requests_of(self, cpf: str) -> list[dict[str, str]]:
        return LimitRequestRepository(self.data_dir / "solicitacoes_aumento_limite.csv").list_for(
            cpf
        )


ScenarioRunner = Callable[..., Run]


@pytest.fixture(scope="session")
def settings() -> Settings:
    file_values = dotenv_values(ENV_FILE)
    values = {name: file_values.get(name) or os.environ.get(name) or None for name in SETTING_NAMES}
    if not values["CHAT_MODEL"] or values["CHAT_MODEL"] == FAKE_MODEL:
        pytest.skip("configure CHAT_MODEL and CHAT_MODEL_API_KEY in .env to run real-model tests")
    return Settings(
        _env_file=None,
        **{name.lower(): value for name, value in values.items()},  # type: ignore[arg-type]
    )


@pytest.fixture(scope="session")
def chat_model(settings: Settings) -> BaseChatModel:
    return build_chat_model(settings, temperature=0, **FAIL_FAST)


@pytest.fixture(scope="session")
def judge_model(settings: Settings) -> BaseChatModel:
    return build_judge_model(settings, temperature=0, **FAIL_FAST)


@pytest.fixture
def run_scenario(
    tmp_path: Path, chat_model: BaseChatModel, judge_model: BaseChatModel
) -> ScenarioRunner:
    counter = iter(range(1000))

    def run(messages: list[str], exchange: object | None = None) -> Run:
        data_dir = tmp_path / f"trial-{next(counter)}"
        data_dir.mkdir()
        bootstrap(data_dir)
        customers = CustomerRepository(data_dir / "clientes.csv")
        bands = ScoreLimitRepository(data_dir / "score_limite.csv")
        graph = build_graph(
            model=chat_model,
            customers=customers,
            bands=bands,
            requests=LimitRequestRepository(data_dir / "solicitacoes_aumento_limite.csv"),
            exchange=exchange or FixedExchange(),  # type: ignore[arg-type]
            guardrail=LocalGuardrail(
                judge=ModelJudge(judge_model), protected=other_customers_patterns(customers, bands)
            ),
            checkpointer=InMemorySaver(),
            clock=lambda: NOW,
        )
        service = ChatService(graph)
        thread = "eval"
        service.start(thread)
        failed = False
        for message in messages:
            if service.is_ended(thread):
                break
            reply = service.send(thread, message)
            if reply.failed:
                reply = service.send(thread, message)
            failed = reply.failed or failed
        history = service.history(thread)
        transcript = "\n".join(
            f"{'Cliente' if role == 'user' else 'Atendente'}: {text}" for role, text in history
        )
        replies = [text for role, text in history if role == "assistant"]
        return Run(transcript, replies, failed, service.is_ended(thread), data_dir)

    return run
