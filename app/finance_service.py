from __future__ import annotations

import asyncio
import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from .idempotency import IdempotencyStore, make_plan_key
from .llm import extract_transaction
from .model_lifecycle import fetch_shutdown_date, openai_model_name, shutdown_warning
from .models import ExtractedTx, NotionTx
from .normalizer import enforce_xor_categories, normalize_account, normalize_outcome
from .notion_gateway import NotionGateway
from .observability import log_event
from .rule_parser import RuleParseResult, parse_with_rules
from .settings import settings
from .taxonomy import set_taxonomy, taxonomy

log = logging.getLogger(__name__)
RuleParserMode = Literal["conservative", "balanced"]

_CONSERVATIVE_OUTCOME_DETAILS = {
    "Benzina",
    "Bollette",
    "Casa",
    "Integratori",
    "Salute",
    "Supermarket",
}
_CONSERVATIVE_INCOME_CATEGORIES = {"Salary"}
_MACRO_CATEGORIES = {"Needs", "Savings", "Wants"}


@dataclass
class SavedTransaction:
    tx: NotionTx
    url: str
    kind: Literal["outcome", "income"]


@dataclass
class ProcessResult:
    saved: list[SavedTransaction]
    parser: Literal["rules", "llm"]
    duplicate: bool = False
    plan_kind: Literal["single", "transfer"] = "single"


class FinanceService:
    def __init__(
        self,
        gateway: NotionGateway | None = None,
        idempotency: IdempotencyStore[ProcessResult] | None = None,
    ) -> None:
        self.gateway = gateway or NotionGateway()
        self.idempotency = idempotency or IdempotencyStore[ProcessResult]()
        # Ultima registrazione per chat (chiave idempotenza + risultato), per /annulla.
        # Solo in memoria: si perde al riavvio del bot.
        self._last_saved: dict[int | None, tuple[str, ProcessResult]] = {}
        # Avviso se OpenAI ha annunciato lo spegnimento di LLM_MODEL (vedi check_model_shutdown).
        self.model_warning: str | None = None

    def bootstrap(self) -> None:
        self.gateway.verify_schema()
        set_taxonomy(self.gateway.read_taxonomy())
        default_account = settings.default_account
        if default_account and default_account not in taxonomy.accounts:
            raise ValueError(
                f"DEFAULT_ACCOUNT '{default_account}' non esiste tra gli account Notion: "
                f"{list(taxonomy.accounts)}"
            )
        log_event(
            log,
            "taxonomy_loaded",
            accounts=len(taxonomy.accounts),
            outcome_categories=len(taxonomy.outcome_categories),
            income_categories=len(taxonomy.income_categories),
        )

    async def process_text(self, text: str, chat_id: int | None = None) -> ProcessResult:
        rule_result = parse_with_rules(text, taxonomy)
        if rule_result and _should_use_rule_result(rule_result, settings.rule_parser_mode):
            parser: Literal["rules", "llm"] = "rules"
            plan = rule_result.transactions
            plan_kind: Literal["single", "transfer"] = (
                "transfer" if rule_result.kind == "transfer" else "single"
            )
        else:
            if rule_result:
                log_event(
                    log,
                    "rule_parser_skipped",
                    mode=settings.rule_parser_mode,
                    kind=rule_result.kind,
                    count=len(rule_result.transactions),
                )
            parser = "llm"
            plan = [await self._extract_with_llm(text)]
            plan_kind = "single"

        key = make_plan_key(chat_id, plan)
        cached = self.idempotency.get(key)
        if cached:
            log_event(log, "duplicate_transaction_skipped", parser=parser, count=len(plan))
            return ProcessResult(
                saved=cached.saved,
                parser=cached.parser,
                duplicate=True,
                plan_kind=cached.plan_kind,
            )

        log_event(log, "transaction_plan_ready", parser=parser, kind=plan_kind, count=len(plan))
        saved = [
            SavedTransaction(
                tx=tx,
                url=await asyncio.to_thread(self.gateway.save_transaction, tx),
                kind="income" if tx.income_categories else "outcome",
            )
            for tx in plan
        ]
        result = ProcessResult(saved=saved, parser=parser, plan_kind=plan_kind)
        self.idempotency.set(key, result)
        self._last_saved[chat_id] = (key, result)
        log_event(log, "transaction_saved", parser=parser, kind=plan_kind, count=len(saved))
        return result

    async def undo_last(self, chat_id: int | None) -> list[SavedTransaction]:
        """Sposta nel cestino di Notion l'ultima registrazione della chat (una sola volta)."""
        entry = self._last_saved.pop(chat_id, None)
        if entry is None:
            return []
        key, result = entry
        try:
            for saved in result.saved:
                await asyncio.to_thread(self.gateway.archive_page, saved.url)
        except Exception:
            # Riprovabile: archiviare di nuovo una pagina gia archiviata non fa danni.
            self._last_saved[chat_id] = entry
            raise
        # Cosi lo stesso messaggio, se reinviato, viene registrato di nuovo.
        self.idempotency.delete(key)
        log_event(log, "transaction_undone", count=len(result.saved))
        return result.saved

    def check_model_shutdown(self, today: dt.date | None = None) -> None:
        """Imposta `model_warning` se OpenAI ha annunciato lo spegnimento di LLM_MODEL.

        Non blocca mai l'avvio: errori di rete o di API vengono solo registrati nei log.
        """
        model = openai_model_name(settings.llm_model)
        api_key = settings.openai_api_key
        if model is None or api_key is None:
            return
        try:
            with httpx.Client(timeout=5.0) as client:
                shutdown = fetch_shutdown_date(model, api_key.get_secret_value(), client)
        except Exception as e:
            log.warning("Controllo spegnimento modello non riuscito: %s", e)
            return
        self.model_warning = shutdown_warning(model, shutdown, today or dt.date.today())
        if self.model_warning:
            log_event(log, "model_shutdown_announced", model=model, shutdown=str(shutdown))

    async def _extract_with_llm(self, text: str) -> NotionTx:
        return notion_tx_from_llm(await extract_transaction(text))


def notion_tx_from_llm(llm_data: dict[str, Any]) -> NotionTx:
    """Normalizza e valida il JSON dell'LLM (usato dal bot e dagli smoke script)."""
    raw = dict(llm_data)

    raw["account"] = normalize_account(
        (raw.get("account") or ""), set(taxonomy.accounts)
    ) or raw.get("account")
    account_is_default = not raw["account"]
    if account_is_default:
        if not settings.default_account:
            # Messaggio intercettato dall'handler Telegram ("Account non valido...").
            raise ValueError("unsupported account: nessun account indicato")
        raw["account"] = settings.default_account
        log_event(log, "default_account_used", account=settings.default_account)

    raw["outcome_categories"] = normalize_outcome(
        raw.get("outcome_categories"),
        raw.get("description", ""),
        set(taxonomy.outcome_categories),
    )

    out_fixed, inc_fixed = enforce_xor_categories(
        description=raw.get("description", ""),
        outcome=raw.get("outcome_categories"),
        income=raw.get("income_categories"),
        allowed_outcome=set(taxonomy.outcome_categories),
        allowed_income=set(taxonomy.income_categories),
    )
    raw["outcome_categories"] = out_fixed
    raw["income_categories"] = inc_fixed

    ext = ExtractedTx.model_validate(raw)
    tx = NotionTx.from_extracted(ext)
    if account_is_default:
        tx.account_is_default = True
    return tx


def _should_use_rule_result(result: RuleParseResult, mode: RuleParserMode) -> bool:
    if mode == "balanced":
        return True

    if result.kind == "transfer":
        return True

    if len(result.transactions) != 1:
        return False

    tx = result.transactions[0]
    if tx.income_categories:
        return set(tx.income_categories).issubset(_CONSERVATIVE_INCOME_CATEGORIES)

    if not tx.outcome_categories:
        return False

    details = set(tx.outcome_categories) - _MACRO_CATEGORIES
    return bool(details) and details.issubset(_CONSERVATIVE_OUTCOME_DETAILS)
