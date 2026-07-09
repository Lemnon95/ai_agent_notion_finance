# AI Project Context

Questo documento spiega il repository a strumenti come Codex, Claude Code o altri agenti di
sviluppo. E pensato per dare contesto architetturale e operativo prima di modificare il codice.

## Descrizione

`ai_agent_notion_finance` e un'app Python che espone un bot Telegram per registrare transazioni
personali in Notion. L'utente invia messaggi come "spesa supermercato 27,90 euro con Hype oggi";
il sistema estrae una transazione strutturata tramite LLM, la valida contro la tassonomia reale
letta da Notion e crea una pagina nel database delle finanze.

Il dominio e in italiano:

- input utente in italiano;
- categorie e account dipendono dai titoli nei database Notion collegati;
- risposta Telegram formattata con descrizione, categorie, account, importo, data e link Notion.

## Architettura In Breve

```text
Telegram text
  -> app.telegram_bot.handle_text
  -> app.finance_service.FinanceService.process_text
  -> app.rule_parser.parse_with_rules
  -> filtro RULE_PARSER_MODE oppure app.llm.extract_transaction
  -> app.normalizer normalizzazioni e XOR, se passa da LLM
  -> app.models.ExtractedTx validazione Pydantic, se passa da LLM
  -> app.models.NotionTx payload interno, una o piu righe
  -> app.idempotency dedupe TTL
  -> app.notion_gateway.NotionGateway.save_transaction
  -> Notion page
  -> app.ux.TxnView confirmation message
```

Il bootstrap legge da Notion la tassonomia consentita:

```text
Notion main DB schema
  -> relation Account / Outcome / Income
  -> related DB page titles in property Name
  -> app.taxonomy.taxonomy singleton
  -> prompt JSON schema, normalizer, Pydantic validators
```

## Moduli

### `main.py`

Entry point minimale:

1. costruisce l'app Telegram tramite `build_application()`;
2. avvia `run_polling()`.

Il bootstrap schema/tassonomia vive in `FinanceService.bootstrap()`, chiamato da
`build_application()`.

### `app/settings.py`

Usa `pydantic-settings` e legge `.env`.

Richiesti:

- `TELEGRAM_BOT_TOKEN`
- `NOTION_TOKEN`
- `NOTION_DB_ID`
- `OPENAI_API_KEY` oppure `GROQ_API_KEY`

Opzionali:

- `LLM_MODEL`
- `TIMEZONE`
- `ENVIRONMENT`
- `RULE_PARSER_MODE`
- `ACCOUNTS`
- `OUTCOME_CATEGORIES`
- `INCOME_CATEGORIES`

Le liste in settings esistono, ma il flusso attuale del bot usa la tassonomia caricata da Notion.
`export_llm_env()` propaga le chiavi LLM in `os.environ` per LiteLLM.

### `app/taxonomy.py`

Contiene:

- dataclass `Taxonomy`;
- singleton mutabile `taxonomy`;
- `set_taxonomy()` che aggiorna le liste in-place;
- `is_taxonomy_loaded()`.

Non riassegnare `taxonomy`, perche altri moduli importano lo stesso oggetto. Aggiornarlo solo con
`set_taxonomy()`.

### `app/notion_gateway.py`

Responsabile di:

- creare `notion_client.Client`;
- leggere proprieta del DB principale;
- verificare tipi minimi con `verify_schema()`;
- leggere titoli dai database relazionati con `read_taxonomy()`;
- risolvere relation per titolo esatto;
- creare pagine Notion con `save_transaction()`.

Schema minimo richiesto nel DB principale:

- `Name`: `title`
- `Amount`: `number`
- `Date`: `date`
- `Account`: `relation`
- `Outcome`: `relation`
- `Income`: `relation`

Le relation devono puntare a database con property title `Name`. `Notes` e opzionale: se
`NotionTx.notes` e valorizzato, il gateway invia `Notes` come `rich_text`.
Se la property `Notes` non esiste e il modello produce note non nulle, la creazione pagina puo
fallire: il prompt tende a usare `null`, ma schema e prompt vanno tenuti allineati.

### `app/llm.py`

Costruisce prompt e JSON schema a runtime, usando `taxonomy`.

Punti importanti:

- `_build_schema()` vincola account/categorie agli enum letti da Notion.
- `_build_system_prompt()` contiene regole di dominio e mapping esempi.
- `_call_llm()` gestisce differenze tra GPT-5 e modelli non GPT-5.
- `extract_transaction()` chiede JSON, rimuove eventuali fence Markdown, fa `json.loads()` e applica
  `enforce_xor_categories()`.

Il file `prompts/expense_parser.md` non e la fonte attiva del prompt runtime; va trattato come
template storico o riferimento.

### `app/normalizer.py`

Livello difensivo prima di Pydantic:

- sinonimi account (`poste` -> `Poste Italiane`, `cash` -> `Contanti`, ecc.);
- sinonimi outcome (`donazione` -> `Gifts & Donations`, ecc.);
- keyword per inferire categorie outcome/income;
- `normalize_account()`;
- `normalize_outcome()`;
- `enforce_xor_categories()`.

Le funzioni mantengono solo valori presenti negli insiemi `allowed`. Questo e importante perche la
tassonomia e dinamica e puo cambiare in Notion.

### `app/models.py`

Contratto validato:

- `ExtractedTx`: output LLM normalizzato e validato.
- `NotionTx`: payload applicativo pronto per il gateway.

Regole:

- `extra = forbid`;
- `description` non vuota;
- `amount > 0`, quantizzato a due decimali;
- `currency` solo `EUR`;
- `account` deve essere nella tassonomia;
- `date` entro un intervallo ragionevole;
- categorie canoniche case-insensitive;
- XOR tra `outcome_categories` e `income_categories`.

### `app/telegram_bot.py`

Orchestra il flusso utente:

- crea o riceve un `FinanceService`;
- `FinanceService.bootstrap()` verifica schema e carica tassonomia;
- `/start` invia testo di aiuto;
- `handle_text()` delega estrazione, normalizzazione, idempotenza e salvataggio al servizio.

La scrittura su Notion e sincrona, quindi viene eseguita dal servizio con `asyncio.to_thread()`.

### `app/finance_service.py`

Servizio applicativo:

- prova prima il parser deterministico;
- in `RULE_PARSER_MODE=conservative` accetta dalle regole solo risultati ad alta confidenza;
- usa l'LLM quando le regole non coprono il testo o quando il mode scarta il risultato;
- costruisce uno o piu `NotionTx`;
- applica idempotenza in-memory a TTL;
- salva su Notion;
- emette log strutturati con `log_event()`.

### `app/rule_parser.py`

Parser deterministico per casi semplici:

- importi e date comuni;
- spese con account e keyword categoria;
- entrate esplicite come stipendio o regalo ricevuto;
- trasferimenti/prelievi con origine e destinazione chiare.

I regali ambigui vengono lasciati all'LLM.

Il parser puro puo riconoscere piu casi di quanti il runtime accetti in modalita conservativa. La
decisione finale e in `FinanceService`, non in `parse_with_rules()`.

### `app/idempotency.py`

Cache in-memory a TTL per evitare duplicati immediati. La chiave deriva da chat e payload
normalizzato delle transazioni. Non e persistente su riavvio processo.

### `app/ux.py`

Contiene helper di presentazione:

- emoji per categorie/account;
- formato importo italiano;
- formato data `DD/MM/YYYY`;
- escape Markdown minimale;
- `TxnView.confirmation_message()`.

### `app/normalize.py`

Contiene preprocessing generico:

- normalizzazione del simbolo euro;
- virgola decimale verso punto;
- risoluzione di "oggi", "ieri", "l'altro ieri".

Al momento non e collegato al flusso principale `handle_text()`. Prima di usarlo, verificare
interazioni con il prompt LLM, che gia riceve "Oggi e YYYY-MM-DD".

### `scripts/`

- `run_bot.py`: avvio polling locale.
- `schema_verify.py`: verifica schema e tassonomia non vuota.
- `taxonomy_dump.py`: stampa tassonomia letta da Notion.
- `smoke_llm.py`: carica tassonomia, chiama LLM, normalizza e valida un input; non salva su Notion.
- `smoke_llm_batch.py`: esegue lo stesso flusso su molti esempi; non salva su Notion.

Gli script richiedono variabili ambiente valide e possono chiamare Notion/LLM reali.

## Comandi Operativi

```bash
make venv
make install
make bot-env
make bot
make schema-verify
make taxonomy-dump
make smoke-llm
make smoke-llm-batch
make lint
make type
make test
make check
```

`make bot-env` fallisce se `.env` non esiste. `make bot` carica `.env` se presente e verifica
`TELEGRAM_BOT_TOKEN`.

`requirements.txt` contiene dipendenze runtime. I target di qualita presuppongono tool come
`ruff`, `black`, `mypy` e `pytest`, che potrebbero dover essere installati a parte.

## Dipendenze Esterne E Side Effect

- Importare moduli che passano da `settings` puo richiedere variabili ambiente valide.
- `build_application()` crea e avvia il bootstrap del `FinanceService`; in test conviene passare un
  servizio finto.
- `schema_verify`, `taxonomy_dump`, `smoke_llm` e `smoke_llm_batch` chiamano servizi esterni.
- `make bot` e `make bot-env` possono scrivere su Notion quando arrivano messaggi Telegram.
- Evitare di eseguire smoke test o bot in CI senza mock o credenziali isolate.

## Strategia Di Test Consigliata

Il repository contiene test unitari per normalizer, modelli, UX, parser regolistico e idempotenza.
Per estenderli:

- testare `app.normalizer` senza LLM/Notion;
- testare `app.models` impostando una tassonomia fittizia con `set_taxonomy()`;
- testare `app.ux` come puro formatting;
- testare `app.rule_parser` con tassonomie piccole e casi ambigui;
- mockare `FinanceService` o `NotionGateway` per handler Telegram;
- evitare chiamate LLM reali nei test automatici.

Per smoke manuali:

- `make schema-verify` prima di modifiche al gateway/schema;
- `make taxonomy-dump` quando cambiano relation o titoli Notion;
- `make smoke-llm` quando cambiano prompt, normalizzatore o modelli;
- `make smoke-llm-batch` per regressioni di classificazione.

## Come Cambiare Il Codice Senza Rompere Il Contratto

### Modifiche a categorie o mapping

Aggiornare `app/normalizer.py` e, se serve, `_build_system_prompt()` in `app/llm.py`. Non assumere
che una categoria esista sempre: controllare `target in allowed`.

### Modifiche al prompt

Conservare:

- output solo JSON;
- valori esatti di account/categorie;
- distinzione spesa/entrata;
- `null` per campi non applicabili;
- schema coerente con `ExtractedTx`.

### Modifiche al modello dati

Aggiornare insieme:

- JSON schema in `app/llm.py`;
- `ExtractedTx`;
- `NotionTx`;
- `NotionGateway.save_transaction()`;
- UX di conferma, se il campo e visibile all'utente.

### Modifiche a Notion

Se cambia il DB:

- aggiornare `verify_schema()`;
- aggiornare relation/property names;
- verificare `read_taxonomy()`;
- eseguire `make schema-verify` e `make taxonomy-dump`.

### Modifiche agli handler Telegram

Mantenere gli handler sottili:

1. leggere testo/chat;
2. delegare a `FinanceService.process_text()`;
3. formattare la risposta;
4. non trasformare errori di conferma Telegram in falsi fallimenti di salvataggio.

## Gotcha Da Tenere Presenti

- Il progetto usa commenti e messaggi misti italiano/inglese, ma il dominio utente e italiano.
- Il typo storico `Eating Out and Takeway` puo essere un titolo Notion reale: non correggerlo a
  `Takeaway` senza migrare la tassonomia.
- `Poste Italiane`, `Other Outcome`, `Other Income`, `Gifts`, `Prelievo` e altre categorie presenti
  nel codice potrebbero non esistere in ogni workspace Notion; il normalizer deve rimanere tollerante.
- `LLM_MODEL` puo essere GPT-5 o altro; `_call_llm()` gestisce parametri diversi.
- Il fallback in `extract_transaction()` riprova con reminder "solo JSON", ma non cambia schema.
- `mypy` e configurato strict: nuove funzioni dovrebbero avere annotazioni complete.
- `line-length` e 100 per Ruff/Black.
