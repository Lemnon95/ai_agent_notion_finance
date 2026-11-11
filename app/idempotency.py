from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from .models import NotionTx


@dataclass
class IdempotencyRecord[T]:
    value: T
    expires_at: float


class IdempotencyStore[T]:
    def __init__(self, ttl_seconds: float = 120.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._records: dict[str, IdempotencyRecord[T]] = {}

    def get(self, key: str) -> T | None:
        self._purge_expired()
        record = self._records.get(key)
        if not record:
            return None
        return record.value

    def set(self, key: str, value: T) -> None:
        self._purge_expired()
        self._records[key] = IdempotencyRecord(
            value=value,
            expires_at=time.monotonic() + self.ttl_seconds,
        )

    def delete(self, key: str) -> None:
        self._records.pop(key, None)

    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired = [key for key, record in self._records.items() if record.expires_at <= now]
        for key in expired:
            del self._records[key]


def _json_default(value: Any) -> str:
    if isinstance(value, Decimal | date):
        return str(value)
    return repr(value)


def make_plan_key(chat_id: int | None, txs: list[NotionTx]) -> str:
    payload = {
        "chat_id": chat_id,
        "transactions": [
            {
                "description": tx.description,
                "amount": tx.amount,
                "date": tx.date,
                "account": tx.account,
                "outcome_categories": tx.outcome_categories,
                "income_categories": tx.income_categories,
                "notes": tx.notes,
            }
            for tx in txs
        ],
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=_json_default)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
