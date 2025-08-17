from __future__ import annotations

from typing import Any, cast

from notion_client import Client

from .models import ALLOWED_ACCOUNTS, NotionTx
from .settings import settings


class NotionGateway:
    def __init__(self) -> None:
        self.client = Client(auth=settings.notion_token.get_secret_value())
        self.db_id = settings.notion_db_id

    @staticmethod
    def _page_url(page_id: str) -> str:
        """Fallback URL stabile se l'API non fornisse 'url'."""
        clean = page_id.replace("-", "")
        return f"https://www.notion.so/{clean}"

    # ---------- VERIFICA SCHEMA / OPZIONI ----------

    def _db_properties(self) -> dict[str, Any]:
        db = cast(dict[str, Any], self.client.databases.retrieve(self.db_id))
        props = db.get("properties", {})
        return cast(dict[str, Any], props)

    @staticmethod
    def _multi_select_options(prop: dict[str, Any]) -> set[str]:
        return {o["name"] for o in prop["multi_select"]["options"]}

    @staticmethod
    def _select_options(prop: dict[str, Any]) -> set[str]:
        return {o["name"] for o in prop["select"]["options"]}

    def verify_schema(self) -> None:
        """
        Verifica che il DB Notion abbia proprietà/tipi attesi e
        che le opzioni per Outcome/Income/Account contengano quelle richieste.
        Se qualcosa non torna, solleva ValueError con dettagli.
        """
        props = self._db_properties()
        errors: list[str] = []
        warnings: list[str] = []

        # Proprietà richieste (nome -> tipo atteso)
        required: dict[str, str] = {
            "Name": "title",
            "Amount": "number",
            "Date": "date",
            "Account": "select",
            "Outcome": "multi_select",
            "Income": "multi_select",
        }

        for name, expected_type in required.items():
            p = props.get(name)
            if p is None:
                errors.append(f"Missing property: '{name}' (expected type '{expected_type}')")
                continue
            actual_type = p.get("type")
            if actual_type != expected_type:
                errors.append(
                    f"Property '{name}' has type '{actual_type}', expected '{expected_type}'"
                )

        # Notes non è obbligatoria: se esiste, controlla che sia rich_text
        p_notes = props.get("Notes")
        if p_notes is not None and p_notes.get("type") != "rich_text":
            warnings.append("Property 'Notes' exists but is not 'rich_text' (optional)")

        # Controllo opzioni Outcome/Income rispetto al .env
        p_out = props.get("Outcome")
        if p_out and p_out.get("type") == "multi_select":
            present = self._multi_select_options(p_out)
            missing_out = [c for c in settings.outcome_categories if c not in present]
            if missing_out:
                errors.append(f"Outcome missing options: {missing_out}")

        p_inc = props.get("Income")
        if p_inc and p_inc.get("type") == "multi_select":
            present = self._multi_select_options(p_inc)
            missing_inc = [c for c in settings.income_categories if c not in present]
            if missing_inc:
                errors.append(f"Income missing options: {missing_inc}")

        # Controllo opzioni Account rispetto agli enum del modello
        p_acc = props.get("Account")
        if p_acc and p_acc.get("type") == "select":
            present = self._select_options(p_acc)
            missing_acc = [a for a in ALLOWED_ACCOUNTS if a not in present]
            if missing_acc:
                errors.append(f"Account missing options: {missing_acc}")

        # Esito
        if errors:
            details = "\n - ".join(errors)
            warn = "\n(warnings)\n - " + "\n - ".join(warnings) if warnings else ""
            raise ValueError(f"Notion DB schema mismatch:\n - {details}{warn}")

        # Se vuoi vedere i warning senza bloccare:
        if warnings:
            # Puoi sostituire con logging.warning(...)
            print("Schema warnings:\n - " + "\n - ".join(warnings))

    # ---------- SAVE TRANSACTION ----------

    def save_transaction(self, tx: NotionTx) -> str:
        """Crea una nuova pagina su Notion per la transazione e restituisce l'URL."""
        properties: dict[str, Any] = {
            # Evita 'Untitled'
            "Name": {
                "title": [{"type": "text", "text": {"content": tx.description or "Transaction"}}]
            },
            "Amount": {"number": float(tx.amount)},
            "Date": {"date": {"start": tx.date.isoformat()}},
            "Account": {"select": {"name": tx.account}},
            "Notes": {
                "rich_text": ([{"type": "text", "text": {"content": tx.notes}}] if tx.notes else [])
            },
        }

        if tx.outcome_categories:
            properties["Outcome"] = {"multi_select": [{"name": c} for c in tx.outcome_categories]}
        if tx.income_categories:
            properties["Income"] = {"multi_select": [{"name": c} for c in tx.income_categories]}

        page = cast(
            dict[str, Any],
            self.client.pages.create(parent={"database_id": self.db_id}, properties=properties),
        )
        url = page.get("url")
        return url if isinstance(url, str) else self._page_url(str(page["id"]))
