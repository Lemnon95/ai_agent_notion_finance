# Guida Per Agenti AI

Queste note valgono per tutto il repository e servono a orientare strumenti come Codex,
Claude Code o agenti simili. Per una spiegazione piu ampia del progetto leggi anche
[`docs/AI_PROJECT_CONTEXT.md`](docs/AI_PROJECT_CONTEXT.md).

## Scopo Del Progetto

`ai_agent_notion_finance` e un bot Telegram Python che registra spese personali in un database
Notion. L'utente scrive una frase naturale in italiano, l'app usa un LLM via LiteLLM per estrarre
una transazione strutturata, valida i dati con Pydantic e crea una pagina nel database Notion.

Stack principale:

- Python 3.12
- `python-telegram-bot` 21.x, async handlers
- Notion API via `notion-client`
- Pydantic v2 e `pydantic-settings`
- LiteLLM per provider LLM OpenAI/Groq
- Ruff, Black, mypy strict

## Mappa Rapida

- `main.py`: entrypoint minimale; costruisce l'app Telegram e avvia il polling.
- `scripts/run_bot.py`: entrypoint pratico per polling locale via `make bot` o `make bot-env`.
- `app/settings.py`: configurazione da `.env`/variabili ambiente. Non leggere o stampare segreti.
- `app/telegram_bot.py`: handler Telegram, orchestrazione del flusso e messaggi utente.
- `app/finance_service.py`: servizio applicativo; sceglie parser regolistico o LLM, applica
  idempotenza e salva su Notion.
- `app/rule_parser.py`: parser deterministico per casi semplici e trasferimenti chiari.
- `app/idempotency.py`: cache TTL in-memory per evitare duplicati immediati.
- `app/observability.py`: helper di logging strutturato.
- `app/llm.py`: prompt runtime, JSON schema dinamico e chiamata LiteLLM.
- `app/models.py`: modelli Pydantic e validazioni di transazione.
- `app/notion_gateway.py`: lettura schema/tassonomia Notion e creazione pagine.
- `app/taxonomy.py`: singleton mutabile con account/categorie lette da Notion.
- `app/normalizer.py`: normalizzazione tollerante di account/categorie e regola XOR.
- `app/normalize.py`: preprocessing testuale legacy/non collegato al flusso runtime attuale.
- `app/ux.py`: formattazione della risposta Telegram.
- `prompts/expense_parser.md`: prompt template storico; il prompt effettivo e in `app/llm.py`.
- `docs/notion-schema.md`: schema Notion umano e regole di trasferimento.
- `scripts/*.py`: diagnostica, smoke test LLM e dump tassonomia.

## Flusso Runtime

1. All'avvio `NotionGateway.verify_schema()` controlla le proprieta minime del database.
2. `NotionGateway.read_taxonomy()` legge account, categorie outcome e income dai DB relazionati.
3. `set_taxonomy()` muta in-place il singleton `taxonomy`; non riassegnarlo.
4. Telegram riceve testo libero tramite `handle_text()`.
5. `FinanceService.process_text()` prova prima `parse_with_rules()`.
6. Se il parser regolistico non copre il caso, `extract_transaction()` usa LLM e JSON schema.
7. Il JSON LLM passa da normalizzazioni difensive in `app/normalizer.py`.
8. `ExtractedTx` valida account, importo, valuta, data e XOR outcome/income.
9. Il servizio applica idempotenza TTL e salva una o piu `NotionTx`.
10. `TxnView` o il messaggio transfer restituiscono conferma Markdown a Telegram.

## Invarianti Da Preservare

- La tassonomia e dinamica: deriva da Notion, non da liste hardcoded nel codice.
- `taxonomy` e un singleton mutabile importato da piu moduli: aggiornalo solo con `set_taxonomy()`.
- Una transazione deve essere outcome oppure income, mai entrambe.
- La valuta ammessa oggi e solo `EUR`.
- `amount` deve essere positivo e viene arrotondato a 2 decimali con `ROUND_HALF_UP`.
- La data deve essere ragionevole: non piu di 3 giorni nel futuro, non piu di 366 giorni nel passato.
- Le relation Notion cercano pagine per titolo esatto nella proprieta `Name`.
- Le API Notion sono sincrone; dentro handler async usa thread separati per chiamate bloccanti.
- Il bot e pensato per frasi e UX in italiano.
- I trasferimenti chiari possono produrre due righe Notion: outcome su account sorgente e income
  su account destinazione.

## Schema Notion Atteso

Database principale:

- `Name`: `title`
- `Amount`: `number`
- `Date`: `date`
- `Account`: `relation`
- `Outcome`: `relation`
- `Income`: `relation`
- `Notes`: opzionale, usata come `rich_text` se presente nel payload

Le relation `Account`, `Outcome` e `Income` devono puntare a database le cui pagine hanno una
proprieta title chiamata `Name`. I titoli di quelle pagine diventano i valori ammessi.
Se `Notes` non esiste e il modello produce note non nulle, la creazione pagina puo fallire: il
prompt tende a usare `null`, ma e un punto da considerare quando si cambia schema o prompt.

## Ambiente

Variabili richieste:

- `TELEGRAM_BOT_TOKEN`
- `NOTION_TOKEN`
- `NOTION_DB_ID`
- almeno una tra `OPENAI_API_KEY` e `GROQ_API_KEY`

Variabili opzionali:

- `LLM_MODEL` default: `gpt-4o-mini-2024-07-18`
- `TIMEZONE` default: `Europe/Rome`
- `ENVIRONMENT` default: `local`
- `ACCOUNTS`, `OUTCOME_CATEGORIES`, `INCOME_CATEGORIES`: presenti in settings, ma il runtime del bot
  usa la tassonomia letta da Notion.

Non committare `.env` e non includere valori segreti nelle risposte.

## Comandi Utili

- `make venv`: crea `.venv` e installa `requirements.txt`.
- `make install`: reinstalla le dipendenze runtime.
- `make bot-env`: avvia il bot caricando `.env`.
- `make bot`: avvia il bot, usando `.env` se presente e verificando `TELEGRAM_BOT_TOKEN`.
- `make schema-verify`: controlla schema e tassonomia Notion.
- `make taxonomy-dump`: stampa account/categorie lette da Notion.
- `make smoke-llm`: estrae e valida una transazione campione senza scrivere su Notion.
- `make smoke-llm-batch`: esegue piu campioni LLM senza scrivere su Notion.
- `make lint`, `make type`, `make test`, `make check`: qualita codice.

Nota: `requirements.txt` contiene soprattutto dipendenze runtime; se mancano `ruff`, `black`,
`mypy` o `pytest`, installarli nell'ambiente di sviluppo prima di usare i target di qualita.

## Linee Guida Per Modifiche

- Prima di cambiare estrazione o categorie, leggi `app/llm.py`, `app/normalizer.py` e
  `app/models.py`: sono tre livelli difensivi dello stesso contratto.
- Se aggiungi sinonimi, mappali verso valori che potrebbero esistere nella tassonomia Notion e
  mantieni i controlli `if target in allowed`.
- Se modifichi il prompt, conserva output solo JSON e usa nomi esatti della tassonomia.
- Se tocchi il salvataggio, mantieni allineati `NotionTx` e `NotionGateway.save_transaction()`.
- Se aggiungi test unitari, preferisci isolare Pydantic/normalizer da Notion e LLM.
- Evita side effect a import time quando possibile: configurazione e accesso Notion partono dal
  bootstrap esplicito del `FinanceService`.

## Rischi E Gotcha

- `build_application()` esegue il bootstrap del `FinanceService`; test e script possono iniettare un
  servizio finto per evitare chiamate Notion reali.
- Il prompt effettivo non viene letto da `prompts/expense_parser.md`; e generato in `app/llm.py`.
- `app/normalize.py` contiene preprocessing utile ma non e usato nel flusso `handle_text()`.
- Gli smoke test chiamano Notion e LLM, quindi richiedono credenziali e possono consumare quota API.
- Il bot vero (`make bot`/`make bot-env`) puo scrivere nuove pagine Notion.
