# app/notion_gateway.py
from __future__ import annotations

from typing import Any, cast

from notion_client import Client

from .models import NotionTx
from .settings import settings
from .taxonomy import Taxonomy


class NotionGateway:
    def __init__(self) -> None:
        self.client = Client(auth=settings.notion_token.get_secret_value())
        self.db_id = settings.notion_db_id
        self._props = self._db_properties()  # cache

    @staticmethod
    def _page_url(page_id: str) -> str:
        clean = page_id.replace("-", "")
        return f"https://www.notion.so/{clean}"

    # ---------- HELPERS DB / PROPS ----------

    def _db_properties(self) -> dict[str, Any]:
        db = cast(dict[str, Any], self.client.databases.retrieve(self.db_id))
        props = cast(dict[str, Any], db.get("properties", {}))
        return props

    def _prop(self, name: str) -> dict[str, Any] | None:
        return cast(dict[str, Any] | None, self._props.get(name))

    def _prop_type(self, name: str) -> str | None:
        p = self._prop(name)
        return None if p is None else cast(str, p.get("type"))

    def _relation_db_id(self, prop_name: str) -> str:
        p = self._prop(prop_name)
        if not p:
            raise ValueError(f"Missing property: '{prop_name}'")
        if p.get("type") != "relation":
            raise ValueError(f"Property '{prop_name}' must be relation")
        rel = cast(dict[str, Any], p.get("relation") or {})
        dbid = cast(str | None, rel.get("database_id"))
        if not dbid:
            raise ValueError(f"{prop_name} is relation but missing 'database_id' metadata")
        return dbid

    # ---------- LIST TITLES FROM RELATED DB ----------

    @staticmethod
    def _extract_title(page: dict[str, Any], title_prop: str = "Name") -> str:
        props = cast(dict[str, Any], page.get("properties", {}))
        tp = cast(dict[str, Any], props.get(title_prop) or {})
        if tp.get("type") != "title":
            return ""
        parts = cast(list[dict[str, Any]], tp.get("title") or [])
        return "".join(p.get("plain_text", "") for p in parts).strip()

    def _list_titles_from_relation(self, prop_name: str, title_prop: str = "Name") -> list[str]:
        db_id = self._relation_db_id(prop_name)
        titles: list[str] = []
        cursor: str | None = None
        while True:
            q = cast(
                dict[str, Any],
                self.client.databases.query(database_id=db_id, start_cursor=cursor, page_size=100),
            )
            for page in cast(list[dict[str, Any]], q.get("results", [])):
                name = self._extract_title(page, title_prop=title_prop)
                if name:
                    titles.append(name)
            if q.get("has_more") and q.get("next_cursor"):
                cursor = cast(str, q["next_cursor"])
                continue
            break
        # dedup preservando ordine
        seen: set[str] = set()
        out: list[str] = []
        for n in titles:
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out

    def read_taxonomy(self) -> Taxonomy:
        """Legge accounts/outcome/income dai DB relazionati (titolo 'Name')."""
        accounts = self._list_titles_from_relation("Account")
        outcome = self._list_titles_from_relation("Outcome")
        income = self._list_titles_from_relation("Income")
        return Taxonomy(accounts=accounts, outcome_categories=outcome, income_categories=income)

    # ---------- VERIFY (tipi base) ----------

    def verify_schema(self) -> None:
        """
        Verifica tipi base:
        - Name: title, Amount: number, Date: date
        - Account/Outcome/Income: relation
        """
        props = self._props
        errors: list[str] = []
        warnings: list[str] = []

        required_exact: dict[str, str] = {
            "Name": "title",
            "Amount": "number",
            "Date": "date",
        }
        for name, expected in required_exact.items():
            p = props.get(name)
            if p is None:
                errors.append(f"Missing property: '{name}' (expected '{expected}')")
                continue
            t = p.get("type")
            if t != expected:
                errors.append(f"Property '{name}' has type '{t}', expected '{expected}'")

        for name in ("Account", "Outcome", "Income"):
            p = props.get(name)
            if p is None:
                errors.append(f"Missing property: '{name}'")
            elif p.get("type") != "relation":
                errors.append(f"Property '{name}' must be relation")

        if errors:
            details = "\n - ".join(errors)
            warn = "\n(warnings)\n - " + "\n - ".join(warnings) if warnings else ""
            raise ValueError(f"Notion DB schema mismatch:\n - {details}{warn}")

        if warnings:
            print("Schema warnings:\n - " + "\n - ".join(warnings))

    # ---------- SAVE TRANSACTION ----------

    def _find_page_id_by_title(self, db_id: str, name: str) -> str | None:
        q = cast(
            dict[str, Any],
            self.client.databases.query(
                database_id=db_id,
                filter={"property": "Name", "title": {"equals": name}},
                page_size=1,
            ),
        )
        results = cast(list[dict[str, Any]], q.get("results", []))
        if results:
            return cast(str, results[0]["id"])
        return None

    def _resolve_relation_ids(
        self, prop_name: str, names: list[str] | None
    ) -> list[dict[str, str]] | None:
        if not names:
            return None
        rel_db = self._relation_db_id(prop_name)
        missing: list[str] = []
        ids: list[dict[str, str]] = []
        for n in names:
            pid = self._find_page_id_by_title(rel_db, n)
            if not pid:
                missing.append(n)
            else:
                ids.append({"id": pid})
        if missing:
            raise ValueError(f"Missing related pages in '{prop_name}' DB for: {missing}")
        return ids

    def save_transaction(self, tx: NotionTx) -> str:
        """Crea una nuova pagina e restituisce l'URL."""
        props: dict[str, Any] = {
            "Name": {
                "title": [{"type": "text", "text": {"content": tx.description or "Transaction"}}]
            },
            "Amount": {"number": float(tx.amount)},
            "Date": {"date": {"start": tx.date.isoformat()}},
        }

        props["Account"] = {"relation": self._resolve_relation_ids("Account", [tx.account]) or []}
        if tx.outcome_categories:
            props["Outcome"] = {
                "relation": self._resolve_relation_ids("Outcome", tx.outcome_categories) or []
            }
        if tx.income_categories:
            props["Income"] = {
                "relation": self._resolve_relation_ids("Income", tx.income_categories) or []
            }
        if tx.notes:
            props["Notes"] = {"rich_text": [{"type": "text", "text": {"content": tx.notes}}]}

        page = cast(
            dict[str, Any],
            self.client.pages.create(parent={"database_id": self.db_id}, properties=props),
        )
        url = page.get("url")
        return url if isinstance(url, str) else self._page_url(str(page["id"]))
