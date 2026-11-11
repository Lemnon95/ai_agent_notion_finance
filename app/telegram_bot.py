# app/telegram_bot.py
from __future__ import annotations

import logging
from typing import Any, cast

from telegram import BotCommand, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .finance_service import FinanceService, ProcessResult, SavedTransaction
from .settings import settings
from .taxonomy import taxonomy
from .ux import TxnView, emoji_for_account, emoji_for_category, escape_md, fmt_amount_eur, fmt_date

log = logging.getLogger(__name__)

HELP_TEXT = (
    "Scrivimi frasi come:\n"
    "• 'ho comprato un caffè 1,20€ con Hype ieri'\n"
    "• 'abbonamento metro 42€ con Revolut oggi'\n"
    "Io estraggo importo, data, account e salvo su Notion.\n"
    "Se ho registrato male, /annulla sposta l'ultima registrazione nel cestino di Notion."
)

BOT_COMMANDS = [
    BotCommand("start", "Come usare il bot"),
    BotCommand("annulla", "Annulla l'ultima registrazione"),
]


# --- HANDLERS ---
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    await msg.reply_text("👋 Ciao! Sono il tuo bot spese su Notion.\n\n" + HELP_TEXT)
    service = cast(FinanceService, context.application.bot_data["finance_service"])
    if service.model_warning:
        await msg.reply_text(service.model_warning)


async def cmd_annulla(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return
    service = cast(FinanceService, context.application.bot_data["finance_service"])
    chat_id = update.effective_chat.id if update.effective_chat else None
    try:
        undone = await service.undo_last(chat_id)
    except Exception as e:
        log.exception("Errore durante /annulla: %s", e)
        await msg.reply_text("❌ Non sono riuscito ad annullare. Riprova o controlla su Notion.")
        return
    if not undone:
        await msg.reply_text("ℹ️ Non c'è nessuna registrazione recente da annullare.")
        return
    await msg.reply_text(_format_undo_message(undone), parse_mode=ParseMode.MARKDOWN)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not msg.text:
        return

    text = msg.text.strip()
    try:
        service = cast(FinanceService, context.application.bot_data["finance_service"])
        chat_id = update.effective_chat.id if update.effective_chat else None
        result = await service.process_text(text, chat_id=chat_id)

    except Exception as e:
        log.exception("Errore durante l'elaborazione del messaggio: %s", e)
        emsg = str(e)
        if "unsupported account" in emsg:
            accounts = ", ".join(taxonomy.accounts) or "un account configurato in Notion"
            user_msg = f"⚠️ Account non valido. Prova a specificare: {accounts}."
        elif "unknown category" in emsg or "provide at least one" in emsg:
            user_msg = (
                "⚠️ Categoria non riconosciuta. Aggiungi dettagli " "(es. 'al bar', 'supermercato')."
            )
        elif "amount must be > 0" in emsg:
            user_msg = "⚠️ L'importo deve essere maggiore di 0."
        elif "date too far" in emsg:
            user_msg = "⚠️ La data sembra troppo lontana: usa oggi/ieri o una data recente."
        else:
            user_msg = "❌ Non sono riuscito a registrare. Riprova riformulando."
        await msg.reply_text(user_msg)
        return

    # Da qui in poi la pagina Notion e gia stata creata: non mandare messaggi di fallimento
    # che potrebbero spingere l'utente a ritentare e duplicare la transazione.
    try:
        await msg.reply_text(
            _format_result_message(result),
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
    except Exception:
        urls = [saved.url for saved in result.saved]
        log.exception("Transazione salvata su Notion, ma invio conferma Telegram fallito: %s", urls)
        return

    await _maybe_send_model_warning(update, context, service)


async def _maybe_send_model_warning(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service: FinanceService
) -> None:
    """Invia l'avviso di spegnimento del modello una volta per chat (per avvio del bot)."""
    msg = update.effective_message
    chat_id = update.effective_chat.id if update.effective_chat else None
    if not service.model_warning or not msg:
        return
    warned = cast(set[int | None], context.application.bot_data.setdefault("model_warned", set()))
    if chat_id in warned:
        return
    warned.add(chat_id)
    try:
        await msg.reply_text(service.model_warning)
    except Exception:
        log.exception("Invio avviso spegnimento modello fallito")


# --- COSTRUZIONE APP (sincrona, mypy-friendly) ---
def _format_result_message(result: ProcessResult) -> str:
    duplicate_prefix = "ℹ️ *Già registrata di recente*\n" if result.duplicate else ""

    if result.plan_kind == "transfer":
        title = "Trasferimento registrato"
        if result.duplicate:
            title = "Trasferimento già registrato di recente"
        lines = [f"✅ *{title}*"]
        for saved in result.saved:
            tx = saved.tx
            categories = tx.outcome_categories or tx.income_categories or []
            cats = " • ".join(f"{emoji_for_category(cat)} {escape_md(cat)}" for cat in categories)
            label = "Entrata" if saved.kind == "income" else "Uscita"
            lines.append(
                f"*{label}* · {emoji_for_account(tx.account)} {escape_md(tx.account)} · "
                f"{fmt_amount_eur(tx.amount)} · {fmt_date(tx.date)}"
            )
            if cats:
                lines.append(cats)
            lines.append(f"🔗 [Apri in Notion]({saved.url})")
        return "\n".join(lines)

    saved = result.saved[0]
    tx = saved.tx
    view = TxnView(
        description=tx.description,
        amount=tx.amount,
        account=tx.account,
        currency="EUR",
        date=tx.date,
        notion_url=saved.url,
        categories=tx.outcome_categories or tx.income_categories or [],
        kind=saved.kind,
        account_is_default=tx.account_is_default,
    )
    return duplicate_prefix + view.confirmation_message()


def _format_undo_message(undone: list[SavedTransaction]) -> str:
    title = "Trasferimento annullato" if len(undone) > 1 else "Registrazione annullata"
    lines = [f"↩️ *{title}*"]
    for saved in undone:
        tx = saved.tx
        lines.append(
            f"{escape_md(tx.description)} · {fmt_amount_eur(tx.amount)} · "
            f"{emoji_for_account(tx.account)} {escape_md(tx.account)}"
        )
    lines.append("🗑️ Spostata nel cestino di Notion: da lì puoi ancora recuperarla.")
    return "\n".join(lines)


async def _post_init(app: Application[Any, Any, Any, Any, Any, Any]) -> None:
    # Menu dei comandi mostrato da Telegram accanto al campo di testo.
    await app.bot.set_my_commands(BOT_COMMANDS)


def build_application(
    service: FinanceService | None = None,
) -> Application[Any, Any, Any, Any, Any, Any]:
    # Carichiamo tassonomia PRIMA di costruire l'app (sincrono)
    finance_service = service or FinanceService()
    finance_service.bootstrap()
    finance_service.check_model_shutdown()

    app = (
        Application.builder()
        .token(settings.telegram_bot_token.get_secret_value())
        .post_init(_post_init)
        .build()
    )
    app.bot_data["finance_service"] = finance_service
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("annulla", cmd_annulla))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return app
