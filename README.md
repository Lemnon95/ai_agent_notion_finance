# ai_agent_notion_finance

A Telegram bot that records personal finance transactions in Notion from natural-language
Italian messages.

For example, the user can send `spesa supermercato 27,90 euro con Hype oggi`; the bot extracts one
or more structured transactions, validates them against the live taxonomy read from Notion, and
creates pages in the `Transactions` database.

## What It Does

- records expenses and income from Telegram;
- reads accounts and categories directly from Notion relations;
- uses deterministic rules for common cases;
- falls back to an LLM for less standard messages;
- handles clear transfers and withdrawals by creating two Notion rows;
- avoids immediate duplicates with an in-memory TTL idempotency cache;
- replies on Telegram with amount, date, account, categories, and the Notion link.

Supported examples:

```text
spesa supermercato 27,90 euro con Hype oggi
stipendio 1820 euro su Revolut
ho ricevuto un regalo 50 euro contanti
prelievo 100 euro da Hype
spostato 200 euro su Risparmio
```

For a clear transfer, the bot can create two rows:

- an `Outcome` row on the source account;
- an `Income` row on the destination account.

## Stack

- Python 3.12
- python-telegram-bot 21.x
- Notion API via `notion-client`
- Pydantic v2
- LiteLLM for OpenAI/Groq
- Ruff, Black, mypy, pytest

## Architecture

```text
Telegram text
  -> app.telegram_bot.handle_text
  -> app.finance_service.FinanceService.process_text
  -> app.rule_parser.parse_with_rules or app.llm.extract_transaction
  -> app.models.ExtractedTx / app.models.NotionTx
  -> app.idempotency
  -> app.notion_gateway.NotionGateway.save_transaction
  -> Notion
```

Main files:

- `app/finance_service.py`: application orchestration, rules/LLM selection, dedupe, and saving.
- `app/rule_parser.py`: deterministic parser for simple cases and clear transfers.
- `app/llm.py`: runtime prompt, dynamic JSON schema, and LiteLLM call.
- `app/models.py`: Pydantic validation.
- `app/normalizer.py`: defensive account/category normalization.
- `app/notion_gateway.py`: Notion schema checks, taxonomy loading, and page creation.
- `app/telegram_bot.py`: Telegram handlers and response flow.
- `app/ux.py`: Telegram message formatting.

AI-agent documentation:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/AI_PROJECT_CONTEXT.md`
- `docs/notion-schema.md`

## Setup

```bash
make venv
```

This creates `.venv` and installs `requirements-dev.txt` (runtime deps plus dev tools).

Dependencies are locked with pip-tools: edit `requirements.in` or `requirements-dev.in`, then run
`make lock` to regenerate the pinned `requirements*.txt` files.

If the virtual environment already exists:

```bash
make install
```

Development tools (`ruff`, `black`, `mypy`, `pytest`) must be available in the virtual environment
for the quality targets.

## Configuration

Create a `.env` file in the project root:

```env
TELEGRAM_BOT_TOKEN=...
NOTION_TOKEN=...
NOTION_DB_ID=...
OPENAI_API_KEY=...
# or GROQ_API_KEY=...

LLM_MODEL=gpt-6-luna
TIMEZONE=Europe/Rome
ENVIRONMENT=local
RULE_PARSER_MODE=conservative
DEFAULT_ACCOUNT=Revolut
```

Required variables:

- `TELEGRAM_BOT_TOKEN`
- `NOTION_TOKEN`
- `NOTION_DB_ID`
- at least one of `OPENAI_API_KEY` or `GROQ_API_KEY`

Optional variables:

- `LLM_MODEL`
- `TIMEZONE`
- `ENVIRONMENT`
- `RULE_PARSER_MODE`: `conservative` by default, or `balanced`
- `DEFAULT_ACCOUNT`: account used when a message names none; must exist in Notion

Do not commit `.env`.

## Notion Schema

The main database must expose these properties:

- `Name`: `title`
- `Amount`: `number`
- `Date`: `date`
- `Account`: `relation`
- `Outcome`: `relation`
- `Income`: `relation`
- `Notes`: optional `rich_text`

The `Account`, `Outcome`, and `Income` relations must point to databases whose title property is
called `Name`. Those page titles become the bot's runtime taxonomy.

Important rule: every transaction must have either `Outcome` or `Income`, never both.

For more detail, see `docs/notion-schema.md`.

## Running

First verify the Notion schema and taxonomy:

```bash
make schema-verify
make taxonomy-dump
```

Start the bot with local polling:

```bash
make bot-env
```

or:

```bash
make bot
```

`make bot-env` requires `.env`. `make bot` loads `.env` when present and checks that
`TELEGRAM_BOT_TOKEN` is set.

## Useful Commands

```bash
make help
make format
make lint
make type
make test
make check
make schema-verify
make taxonomy-dump
make smoke-llm
make smoke-llm-batch
make bot-env
make bot
```

Notes:

- `make check` runs linting, type checking, and tests.
- `make smoke-llm` and `make smoke-llm-batch` call real Notion and LLM services, but do not create
  Notion pages.
- `make bot` and `make bot-env` can create new Notion pages when Telegram messages arrive.

## Tests

```bash
make check
```

The test suite covers:

- account/category normalization;
- Pydantic validation;
- Telegram UX formatting;
- deterministic rule parsing;
- idempotency;
- `FinanceService` orchestration with a fake gateway.

## Domain Notes

- The taxonomy is not hardcoded as the source of truth: it is read from Notion at bootstrap.
- The rule parser runs in conservative mode by default: only whitelisted, high-confidence rule
  results are saved directly; everything else falls back to the LLM.
- Set `RULE_PARSER_MODE=balanced` to trust the rule parser on a wider set of categories.
- Transfers between accounts can be represented as two rows in the same Notion database.
- `Eating Out and Takeway` is intentionally spelled that way because it may be the real Notion
  title.
- Current idempotency is in-memory: it prevents close retries, but does not survive a process
  restart.

## Project Direction

The project is meant to be a pragmatic personal assistant: Notion remains the place to inspect,
audit, and correct data; Telegram is the fast input surface; the code applies validation and
guardrails before writing.

The recommended direction is to keep moving frequent cases into deterministic rules and use the
LLM as an intelligent fallback.
