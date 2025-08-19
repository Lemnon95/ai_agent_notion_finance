from __future__ import annotations

from typing import Any, cast

from notion_client import Client

from .models import ALLOWED_ACCOUNTS, NotionTx
from .settings import settings


class NotionGateway:
    def __init__(self) -> None:
        self.client = Client(auth=settings.notion_token.get_secret_value())
        self.db_id = settings.notion_db_id
        self._props = self._db_properties()  # cache

    @staticmethod
    def _page_url(page_id: str) -> str:
        """Fallback URL stabile se l'API non fornisse 'url'."""
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

    def _find_page_id_by_title(self, db_id: str, name: str) -> str | None:
        # Assumiamo che la property titolo del DB relazionato si chiami "Name"
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
        self,
        prop_name: str,
        names: list[str] | None,
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

    # ---------- VERIFICA SCHEMA / OPZIONI ----------

    def verify_schema(self) -> None:
        """
        Verifica che il DB Notion abbia proprietà/tipi attesi:
        - Name: title, Amount: number, Date: date
        - Account/Outcome/Income: relation (e che i DB relazionati contengano
          le pagine richieste)
        """
        props = self._props
        errors: list[str] = []
        warnings: list[str] = []

        # Base obbligatorie (tipi esatti)
        required_exact: dict[str, str] = {
            "Name": "title",
            "Amount": "number",
            "Date": "date",
        }
        for name, expected_type in required_exact.items():
            p = props.get(name)
            if p is None:
                errors.append(f"Missing property: '{name}' (expected type '{expected_type}')")
                continue
            actual_type = p.get("type")
            if actual_type != expected_type:
                errors.append(
                    f"Property '{name}' has type '{actual_type}', expected '{expected_type}'"
                )

        # Notes opzionale ma raccomandata rich_text
        p_notes = props.get("Notes")
        if p_notes is not None and p_notes.get("type") != "rich_text":
            warnings.append("Property 'Notes' exists but is not 'rich_text' (optional)")

        # Account relation: devono esistere pagine per tutti gli account
        try:
            acc_db = self._relation_db_id("Account")
            missing_acc: list[str] = []
            for a in ALLOWED_ACCOUNTS:
                if not self._find_page_id_by_title(acc_db, a):
                    missing_acc.append(a)
            if missing_acc:
                errors.append(f"Account relation missing pages: {missing_acc}")
        except ValueError as e:
            errors.append(str(e))

        # Outcome relation
        try:
            out_db = self._relation_db_id("Outcome")
            missing_out: list[str] = []
            for c in settings.outcome_categories:
                if not self._find_page_id_by_title(out_db, c):
                    missing_out.append(c)
            if missing_out:
                errors.append(f"Outcome relation missing pages: {missing_out}")
        except ValueError as e:
            errors.append(str(e))

        # Income relation
        try:
            inc_db = self._relation_db_id("Income")
            missing_inc: list[str] = []
            for c in settings.income_categories:
                if not self._find_page_id_by_title(inc_db, c):
                    missing_inc.append(c)
            if missing_inc:
                errors.append(f"Income relation missing pages: {missing_inc}")
        except ValueError as e:
            errors.append(str(e))

        if errors:
            details = "\n - ".join(errors)
            warn = "\n(warnings)\n - " + "\n - ".join(warnings) if warnings else ""
            raise ValueError(f"Notion DB schema mismatch:\n - {details}{warn}")

        if warnings:
            print("Schema warnings:\n - " + "\n - ".join(warnings))

    # ---------- SAVE TRANSACTION ----------

    def save_transaction(self, tx: NotionTx) -> str:
        """Crea una nuova pagina e restituisce l'URL."""
        props: dict[str, Any] = {
            "Name": {
                "title": [{"type": "text", "text": {"content": tx.description or "Transaction"}}]
            },
            "Amount": {"number": float(tx.amount)},
            "Date": {"date": {"start": tx.date.isoformat()}},
        }

        # Account relation (singolo)
        acc_rel = self._resolve_relation_ids("Account", [tx.account]) or []
        props["Account"] = {"relation": acc_rel}

        # Outcome relation (lista)
        if tx.outcome_categories:
            out_rel = self._resolve_relation_ids("Outcome", tx.outcome_categories) or []
            props["Outcome"] = {"relation": out_rel}

        # Income relation (lista)
        if tx.income_categories:
            inc_rel = self._resolve_relation_ids("Income", tx.income_categories) or []
            props["Income"] = {"relation": inc_rel}

        if tx.notes:
            props["Notes"] = {"rich_text": [{"type": "text", "text": {"content": tx.notes}}]}

        page = cast(
            dict[str, Any],
            self.client.pages.create(
                parent={"database_id": self.db_id},
                properties=props,
            ),
        )
        url = page.get("url")
        return url if isinstance(url, str) else self._page_url(str(page["id"]))
