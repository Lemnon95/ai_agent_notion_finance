from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

from .idempotency import IdempotencyStore, make_plan_key
from .llm import extract_transaction
from .models import ExtractedTx, NotionTx
from .normalizer import enforce_xor_categories, normalize_account, normalize_outcome
from .notion_gateway import NotionGateway
from .observability import log_event
from .rule_parser import parse_with_rules
from .taxonomy import set_taxonomy, taxonomy

log = logging.getLogger(__name__)


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

    def bootstrap(self) -> None:
        self.gateway.verify_schema()
        set_taxonomy(self.gateway.read_taxonomy())
        log_event(
            log,
            "taxonomy_loaded",
            accounts=len(taxonomy.accounts),
            outcome_categories=len(taxonomy.outcome_categories),
            income_categories=len(taxonomy.income_categories),
        )

    async def process_text(self, text: str, chat_id: int | None = None) -> ProcessResult:
        rule_result = parse_with_rules(text, taxonomy)
        if rule_result:
            parser: Literal["rules", "llm"] = "rules"
            plan = rule_result.transactions
            plan_kind: Literal["single", "transfer"] = (
                "transfer" if rule_result.kind == "transfer" else "single"
            )
        else:
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
        log_event(log, "transaction_saved", parser=parser, kind=plan_kind, count=len(saved))
        return result

    async def _extract_with_llm(self, text: str) -> NotionTx:
        raw = await extract_transaction(text)

        raw["account"] = normalize_account(
            (raw.get("account") or ""), set(taxonomy.accounts)
        ) or raw.get("account")

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
        return NotionTx.from_extracted(ext)
