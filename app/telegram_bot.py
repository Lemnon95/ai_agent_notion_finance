# app/telegram_bot.py
from __future__ import annotations

import asyncio
import logging
from typing import Any

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .llm import extract_transaction
from .models import ExtractedTx, NotionTx
from .normalizer import enforce_xor_categories, normalize_account, normalize_outcome
from .notion_gateway import NotionGateway
from .settings import settings
from .taxonomy import set_taxonomy, taxonomy

log = logging.getLogger(__name__)
gateway = NotionGateway()

HELP_TEXT = (
    "Scrivimi frasi come:\n"
    "• 'ho comprato un caffè 1,20€ con Hype ieri'\n"
    "• 'abbonamento metro 42€ con Revolut oggi'\n"
    "Io estraggo importo, data, account e salvo su Notion."
)


# --- BOOTSTRAP SINCRONO (niente task/await) ---
def bootstrap_taxonomy() -> None:
    """Carica tassonomia da Notion all'avvio (sincrono)."""
    gateway.verify_schema()
    set_taxonomy(gateway.read_taxonomy())
    log.info(
        "Taxonomy loaded: %d accounts, %d outcome, %d income",
        len(taxonomy.accounts),
        len(taxonomy.outcome_categories),
        len(taxonomy.income_categories),
    )


# --- HANDLERS ---
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    await msg.reply_text("👋 Ciao! Sono il tuo bot spese su Notion.\n\n" + HELP_TEXT)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not msg.text:
        return

    text = msg.text.strip()
    try:
        # 1) Estrazione LLM
        raw: dict[str, Any] = await extract_transaction(text)

        # 2) Normalizzazione PRE-validazione
        raw["account"] = normalize_account(
            (raw.get("account") or ""), set(taxonomy.accounts)
        ) or raw.get("account")

        raw["outcome_categories"] = normalize_outcome(
            raw.get("outcome_categories"),
            raw.get("description", ""),
            set(taxonomy.outcome_categories),
        )

        # 3) Enforce XOR (evita income+outcome insieme)
        out_fixed, inc_fixed = enforce_xor_categories(
            description=raw.get("description", ""),
            outcome=raw.get("outcome_categories"),
            income=raw.get("income_categories"),
            allowed_outcome=set(taxonomy.outcome_categories),
            allowed_income=set(taxonomy.income_categories),
        )
        raw["outcome_categories"] = out_fixed
        raw["income_categories"] = inc_fixed

        # 4) Validazione
        ext = ExtractedTx.model_validate(raw)

        # 5) Costruzione payload Notion
        notion_tx = NotionTx.from_extracted(ext)

        # 6) Salvataggio Notion (sync) in thread separato
        url = await asyncio.to_thread(gateway.save_transaction, notion_tx)

        # 7) Risposta utente
        amount_eur = f"{notion_tx.amount:.2f}".replace(".", ",")
        cats = notion_tx.outcome_categories or notion_tx.income_categories or []
        cats_s = ", ".join(cats) if cats else "—"
        reply = (
            "✅ Spesa/Movimento registrato\n"
            f"• Descrizione: {notion_tx.description}\n"
            f"• Importo: {amount_eur} €\n"
            f"• Data: {notion_tx.date.isoformat()}\n"
            f"• Account: {notion_tx.account}\n"
            f"• Categoria/e: {cats_s}\n\n"
            f'🔗 <a href="{url}">Apri in Notion</a>'
        )
        await msg.reply_html(reply, disable_web_page_preview=True)

    except Exception as e:
        log.exception("Errore durante l'elaborazione del messaggio: %s", e)
        emsg = str(e)
        if "unsupported account" in emsg:
            user_msg = "⚠️ Account non valido. Prova a specificare Hype, Revolut o Contanti."
        elif "unknown category" in emsg or "provide at least one" in emsg:
            user_msg = (
                "⚠️ Categoria non riconosciuta. Aggiungi dettagli (es. 'al bar', 'supermercato')."
            )
        elif "amount must be > 0" in emsg:
            user_msg = "⚠️ L'importo deve essere maggiore di 0."
        elif "date too far" in emsg:
            user_msg = "⚠️ La data sembra troppo lontana: usa oggi/ieri o una data recente."
        else:
            user_msg = "❌ Non sono riuscito a registrare. Riprova riformulando."
        await msg.reply_text(user_msg)


# --- COSTRUZIONE APP (sincrona, mypy-friendly) ---
def build_application() -> Application:
    # Carichiamo tassonomia PRIMA di costruire l'app (sincrono)
    bootstrap_taxonomy()

    app = Application.builder().token(settings.telegram_bot_token.get_secret_value()).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return app
