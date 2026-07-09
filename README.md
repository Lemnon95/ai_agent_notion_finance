# ai_agent_notion_finance

Bot Telegram per registrare transazioni personali in Notion a partire da frasi naturali in
italiano.

L'utente scrive, per esempio, `spesa supermercato 27,90 euro con Hype oggi`; il bot estrae una o
piu transazioni strutturate, le valida contro la tassonomia reale letta da Notion e crea le pagine
nel database `Transactions`.

## Cosa Fa

- registra spese e entrate da Telegram;
- legge account e categorie direttamente dalle relation Notion;
- usa regole deterministiche per i casi frequenti;
- usa un LLM come fallback per frasi meno standard;
- gestisce trasferimenti/prelievi chiari creando due righe Notion;
- evita duplicati immediati con una cache di idempotenza a TTL;
- conferma su Telegram con importo, data, account, categorie e link Notion.

Esempi supportati:

```text
spesa supermercato 27,90€ con Hype oggi
stipendio 1820€ su Revolut
ho ricevuto un regalo 50€ contanti
prelievo 100€ da Hype
spostato 200€ su Risparmio
```

Per un trasferimento chiaro, il bot puo creare due righe:

- `Outcome` sull'account di origine;
- `Income` sull'account di destinazione.

## Stack

- Python 3.12
- python-telegram-bot 21.x
- Notion API via `notion-client`
- Pydantic v2
- LiteLLM per OpenAI/Groq
- Ruff, Black, mypy, pytest

## Architettura

```text
Telegram text
  -> app.telegram_bot.handle_text
  -> app.finance_service.FinanceService.process_text
  -> app.rule_parser.parse_with_rules oppure app.llm.extract_transaction
  -> app.models.ExtractedTx / app.models.NotionTx
  -> app.idempotency
  -> app.notion_gateway.NotionGateway.save_transaction
  -> Notion
```

File principali:

- `app/finance_service.py`: orchestrazione applicativa, parser rules/LLM, dedupe e salvataggio.
- `app/rule_parser.py`: parser deterministico per casi semplici e trasferimenti chiari.
- `app/llm.py`: prompt runtime, schema JSON dinamico e chiamata LiteLLM.
- `app/models.py`: validazione Pydantic.
- `app/normalizer.py`: normalizzazione difensiva di account/categorie.
- `app/notion_gateway.py`: schema Notion, tassonomia e creazione pagine.
- `app/telegram_bot.py`: handler Telegram e UX di risposta.
- `app/ux.py`: formattazione messaggi Telegram.

Documentazione per agenti AI:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/AI_PROJECT_CONTEXT.md`
- `docs/notion-schema.md`

## Setup

```bash
make venv
```

Il comando crea `.venv` e installa `requirements.txt`.

Se la venv esiste gia:

```bash
make install
```

I tool di sviluppo (`ruff`, `black`, `mypy`, `pytest`) devono essere disponibili nella venv per i
target di qualita.

## Configurazione

Crea un file `.env` nella root del progetto:

```env
TELEGRAM_BOT_TOKEN=...
NOTION_TOKEN=...
NOTION_DB_ID=...
OPENAI_API_KEY=...
# oppure GROQ_API_KEY=...

LLM_MODEL=gpt-4o-mini-2024-07-18
TIMEZONE=Europe/Rome
ENVIRONMENT=local
```

Variabili richieste:

- `TELEGRAM_BOT_TOKEN`
- `NOTION_TOKEN`
- `NOTION_DB_ID`
- almeno una tra `OPENAI_API_KEY` e `GROQ_API_KEY`

Variabili opzionali:

- `LLM_MODEL`
- `TIMEZONE`
- `ENVIRONMENT`

Non committare `.env`.

## Schema Notion

Il database principale deve avere queste proprieta:

- `Name`: `title`
- `Amount`: `number`
- `Date`: `date`
- `Account`: `relation`
- `Outcome`: `relation`
- `Income`: `relation`
- `Notes`: opzionale, `rich_text`

Le relation `Account`, `Outcome` e `Income` devono puntare a database con una title property
chiamata `Name`. I titoli di quelle pagine diventano la tassonomia runtime del bot.

Regola importante: ogni transazione deve avere `Outcome` oppure `Income`, mai entrambe.

Per dettagli piu completi: `docs/notion-schema.md`.

## Avvio

Verifica prima schema e tassonomia Notion:

```bash
make schema-verify
make taxonomy-dump
```

Avvia il bot in polling locale:

```bash
make bot-env
```

oppure:

```bash
make bot
```

`make bot-env` richiede `.env`. `make bot` carica `.env` se presente e verifica che
`TELEGRAM_BOT_TOKEN` sia impostato.

## Comandi Utili

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

Note:

- `make check` esegue lint, typecheck e test.
- `make smoke-llm` e `make smoke-llm-batch` chiamano Notion e LLM reali, ma non scrivono pagine.
- `make bot` e `make bot-env` possono scrivere nuove pagine Notion quando arrivano messaggi
  Telegram.

## Test

```bash
make check
```

La suite copre:

- normalizzazione account/categorie;
- validazione Pydantic;
- UX Telegram;
- parser deterministico;
- idempotenza;
- orchestrazione `FinanceService` con gateway finto.

## Note Di Dominio

- La tassonomia non e hardcoded come fonte di verita: viene letta da Notion al bootstrap.
- Il parser regolistico gestisce solo casi chiari; frasi ambigue passano all'LLM.
- I trasferimenti tra account possono essere rappresentati come due righe nello stesso database.
- `Eating Out and Takeway` e scritto cosi perche puo essere il titolo reale in Notion.
- L'idempotenza attuale e in-memory: evita retry ravvicinati, ma non sopravvive a un riavvio.

## Stato Del Progetto

Il progetto e pensato come assistente personale pragmatico: Notion rimane il luogo dove leggere,
controllare e correggere i dati; Telegram e l'interfaccia rapida; il codice applica controlli
prima di scrivere.

La direzione consigliata e continuare a spostare i casi frequenti verso regole deterministiche e
lasciare l'LLM come fallback intelligente.
