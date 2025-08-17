from __future__ import annotations

import logging
from typing import Any, cast

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    JobQueue,
    MessageHandler,
    filters,
)

from .llm import extract_transaction
from .models import ExtractedTx, NotionTx
from .normalize import preprocess
from .notion_gateway import NotionGateway
from .settings import settings

log = logging.getLogger(__name__)
gateway = NotionGateway()

HELP_TEXT = (
    "Scrivimi frasi come: \n"
    "• 'ho comprato un caffè 1,20€ con Hype ieri'\n"
    "• 'abbonamento metro 42 con Revolut oggi'\n"
    "Io estraggo importo, data, conto e salvo su Notion."
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return
    await message.reply_text("👋 Ciao! Sono il tuo bot spese su Notion.\n" + HELP_TEXT)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.text:
        return

    text = preprocess(message.text.strip())
    try:
        raw = await extract_transaction(text)
        ext = ExtractedTx.model_validate(raw)
        notion_tx = NotionTx.from_extracted(ext)

        url = gateway.save_transaction(notion_tx)  # sync

        amount_eur = f"{notion_tx.amount:.2f}".replace(".", ",")
        reply = (
            "✅ Spesa/Movimento registrato\n"
            f"• Descrizione: {notion_tx.description}\n"
            f"• Importo: {amount_eur} €\n"
            f"• Data: {notion_tx.date.isoformat()}\n"
            f"• Account: {notion_tx.account}\n"
        )
        if notion_tx.outcome_categories:
            reply += f"• Outcome: {', '.join(notion_tx.outcome_categories)}\n"
        if notion_tx.income_categories:
            reply += f"• Income: {', '.join(notion_tx.income_categories)}\n"
        reply += f'\n🔗 <a href="{url}">Apri in Notion</a>'

        await message.reply_html(reply, disable_web_page_preview=True)

    except Exception:
        log.exception("Errore durante l'elaborazione del messaggio")
        await message.reply_text(
            "⚠️ Non sono riuscito a registrare la spesa.\n"
            "- Controlla account (Hype/Revolut/Contanti) e importo (>0).\n"
            "- Data non troppo nel futuro/passato.\n"
            "Se persiste, riprova riformulando la frase."
        )


# Alias di tipo con i 6 parametri generici (Python 3.12: keyword `type`)
type AppT = Application[
    Any,
    Any,
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    JobQueue[Any] | None,
]


def build_application() -> AppT:
    token = settings.telegram_bot_token.get_secret_value()
    app = Application.builder().token(token).build()
    app_typed: AppT = cast(AppT, app)

    app_typed.add_handler(CommandHandler("start", cmd_start))
    app_typed.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return app_typed
