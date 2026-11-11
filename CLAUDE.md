# Claude Project Notes

Questo repository e un bot Telegram per registrare spese personali in Notion usando estrazione LLM.
Leggi anche [`AGENTS.md`](AGENTS.md) e [`docs/AI_PROJECT_CONTEXT.md`](docs/AI_PROJECT_CONTEXT.md):
sono la documentazione operativa condivisa per agenti AI.

## Priorita

- Mantieni il comportamento utente in italiano.
- Non leggere, stampare o committare segreti da `.env`.
- Non hardcodare tassonomie come fonte di verita: account e categorie arrivano dalle relation Notion.
- Preserva la regola XOR: una transazione e `Outcome` oppure `Income`, mai entrambe.
- Il runtime usa `RULE_PARSER_MODE=conservative` di default: non assumere che ogni risultato del
  parser regolistico venga salvato senza passare dall'LLM.
- Ricorda che Notion e sincrono; dentro handler async usa `asyncio.to_thread()` per scritture/chiamate
  bloccanti.

## File Da Guardare Per Primi

- `app/telegram_bot.py`: orchestrazione end-to-end del messaggio Telegram.
- `app/finance_service.py`: servizio applicativo, idempotenza e salvataggio.
- `app/rule_parser.py`: parser deterministico per casi semplici e trasferimenti chiari.
- `app/llm.py`: prompt runtime, schema JSON dinamico e chiamata LiteLLM.
- `app/models.py`: contratto Pydantic finale della transazione.
- `app/normalizer.py`: fallback e correzioni prima della validazione.
- `app/notion_gateway.py`: schema Notion, tassonomia e salvataggio pagine.
- `app/taxonomy.py`: singleton mutabile; usare `set_taxonomy()`, non riassegnare `taxonomy`.

## Comandi

- Setup: `make venv`
- Avvio bot con `.env`: `make bot-env`
- Schema Notion: `make schema-verify`
- Tassonomia Notion: `make taxonomy-dump`
- Smoke singolo LLM: `make smoke-llm`
- Smoke batch LLM: `make smoke-llm-batch`
- Qualita: `make lint`, `make type`, `make test`, `make check`

Gli smoke test usano Notion e LLM reali ma non scrivono pagine; il bot puo scrivere nel database Notion.

## Schema Minimo Notion

Il DB principale deve avere `Name` title, `Amount` number, `Date` date e relation `Account`,
`Outcome`, `Income`. I database relazionati devono avere una title property `Name`; quei titoli
sono i valori ammessi a runtime.

## Note Di Implementazione

- Il prompt LLM attivo e generato in `app/llm.py` (`_build_system_prompt()`).
- `build_application()` esegue il bootstrap del `FinanceService`; per testare handler o UX conviene
  iniettare un servizio finto.
- Dipendenze: modifica `requirements.in`/`requirements-dev.in` e lancia `make lock`; i
  `requirements*.txt` sono lockfile generati da pip-tools, non editarli a mano.
- `.claude/settings.json` nega la lettura di `.env` e chiede conferma per i target che usano
  Notion/LLM/Telegram reali.
