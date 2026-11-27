# FinanceGuardian: Budget, Regole E Analisi Nel Bot

**Data:** 2026-11-27
**Stato:** visione concordata, **non implementata**. Restano domande aperte (sotto) da chiudere
prima di scrivere il motore.

## Origine

L'utente ha proposto "FinanceGuardian", una specifica ampia per un sistema di controllo delle
finanze personali: regole di budget, analisi, consulente AI, notifiche, dashboard. La specifica
originale non e salvata nel repository; questo documento ne raccoglie la versione ridotta e
concordata.

Idea di fondo, che resta valida: non basta sapere dove sono finiti i soldi, il sistema deve
aiutare a decidere *mentre* si spende. I calcoli sono deterministici; l'AI interpreta e
suggerisce, non calcola.

## Visione Del Prodotto

Un solo bot Telegram, quello esistente, con in piu un "controllore" che legge le spese da Notion
e dice come si sta andando.

**1. Feedback a ogni spesa registrata** (novita principale):

```
Tu:   glovo 22 euro revolut
Bot:  ✅ Glovo — 22,00 € — Revolut — Eating Out
      🛵 Delivery: 3 / 2 ordini — ❌ superato
```

**2. Stato del mese su richiesta:**

```
Tu:   /budget
Bot:  Novembre 2026 (al 20)
      ⚠️ Cibo fuori casa    134 € / 150 €
      ❌ Delivery           3 / 2 ordini
      ✅ AI e abbonamenti    48 € / 70 €
      ✅ Barbiere           1 / 2 visite
      ⏳ Risparmio          250 € / 420 € (si valuta a fine mese)
```

**3. Report mensile riconciliato:**

```
Tu:   /report 2026-11
Bot:  Uscite lorde      3.540 €
       − trasferimenti  1.800 €
       − poker             50 €
       − rettifiche        40 €   ⚠️ senza causale
      = Spese effettive 1.650 €
```

Tutti gli importi in questo documento sono inventati.

**4. Poi: consigli AI** (Phase 3). L'LLM riceve solo il report strutturato e aggregato e propone
azioni; una proposta accettata diventa una regola.

```
Bot:  💡 Cibo fuori casa e il budget piu sforato (+30 €).
      3 dei 7 pasti fuori sono delivery il venerdi sera.
      Proposta: "max 1 delivery a settimana" → ~25 €/mese.
      [Accetta] [Ignora]
```

**5. Poi: avvisi automatici** (Phase 2): rinnovi abbonamenti, report settimanale. Dipendono
dall'hosting.

**6. Poi: dashboard visiva come Telegram Mini App** (Phase 4), al posto di una web app separata.

## Decisioni Prese

Concordate con l'approvazione della visione:

| Decisione | Motivo |
|---|---|
| Stesso repository e stesso bot, non un progetto nuovo | Notion, tassonomia runtime e Telegram sono gia qui; il bot scrive, il nuovo modulo legge |
| Notion resta l'unica fonte dati; niente DB locale nell'MVP | Poche centinaia di movimenti al mese: rileggere il periodo da Notion costa pochi secondi ed e idempotente per costruzione. Evita sync incrementale, cancellazioni, riconciliazione, migrazioni |
| Calcoli solo nel codice, mai nell'LLM | Riproducibili e testabili |
| Regole in un file di configurazione, non nel codice | Cambiare un limite = cambiare un numero |
| Telegram e l'interfaccia; niente CLI dedicata ne web app | Gia in uso sullo smartphone; per lo sviluppo basta uno script in `scripts/` con target `make` |
| Dashboard futura come Telegram Mini App | Autenticazione gratis tramite `initData` firmato da Telegram; un solo canale |
| Il DB `Months` di Notion non viene usato per i calcoli | Puo non essere aggiornato; i totali si ricalcolano dalle transazioni |

Scartato dalla specifica originale, perche prematuro per un singolo utente: FastAPI, React,
SQLAlchemy/Alembic, Typer, uv (il repo usa pip-tools), Docker, APScheduler, pandas (peggiora il
problema dei 250 MB su Lambda), una tassonomia parallela di ~25 categorie con pipeline di
classificazione a 7 livelli.

## Proposte Tecniche

Da confermare quando si implementa, ma gia ragionate.

### Struttura

```
app/
  (lato scrittura esistente: invariato)
  notion_gateway.py   + query_transactions(start, end)   # sola lettura, paginata
  analysis/           # puro: niente I/O, niente LLM
    ledger.py         # LedgerEntry (Decimal) + assegnazione del tipo
    rules.py          # modelli Pydantic delle regole + evaluate()
    report.py         # MonthReport strutturato
config/finance_rules.toml   # tomllib e in stdlib: zero dipendenze nuove
```

Il motore restituisce oggetti strutturati e serializzabili (`MonthReport`), mai testo gia
formattato: Telegram, l'LLM e la futura Mini App leggono lo stesso oggetto.

### Classificazione Delle Righe

Ogni riga Notion riceve esattamente un tipo: `expense`, `income`, `transfer`, `savings`, `poker`,
`adjustment`, `unclassified`. Le categorie Notion restano la tassonomia; per le distinzioni che
non coprono (delivery, DeepSeek, barbiere) si usano tag a parole chiave sul `Name`, definiti in
configurazione. Le categorie e i tag servono da filtri delle regole; non dividono le righe in
gruppi, quindi una riga puo soddisfare piu regole.

### Regole

Tre tipi per l'MVP:

- `spending_limit`: somma degli importi filtrati ≤ limite (copre anche il "merchant limit" con un
  filtro per tag);
- `count_limit`: numero di transazioni filtrate ≤ limite;
- `minimum_savings`: obiettivo minimo, valutato a fine periodo.

Stati: `OK`, `WARNING` (soglia, es. 80%), `LIMIT_REACHED`, `VIOLATED`, `PENDING` (obiettivo minimo
a periodo non concluso), `UNKNOWN` (dati mancanti o errore Notion), `DISABLED`.

Anomalie (rettifiche senza causale, righe non classificate) non sono regole: sono controlli che
compaiono nel report.

Esempio di configurazione:

```toml
[classification]
transfer_categories = ["Prelievo", "Risparmio"]
savings_accounts    = ["Risparmio"]          # da confermare, vedi domande aperte

[tags]
delivery = ["deliveroo", "glovo", "just eat"]
deepseek = ["deepseek"]
barbiere = ["barbiere"]

[[rules]]
id = "cibo-fuori"
name = "Cibo fuori casa"
type = "spending_limit"
filter = { outcome_any = ["Eating Out and Takeway"] }
limit = "150.00"
warn_at = 0.8

[[rules]]
id = "delivery"
name = "Delivery"
type = "count_limit"
filter = { tags_any = ["delivery"] }
limit = 2
```

### Regole Iniziali Dell'Utente

| Regola | Limite | Periodo |
|---|---:|---|
| Cibo fuori casa | 150 € | mensile |
| Delivery | 2 ordini | mensile |
| Casa e abbigliamento | 150 € | mensile |
| AI e abbonamenti discrezionali (escluso piano telefonico) | 70 € | mensile |
| Crediti DeepSeek | 10 € | mensile |
| Barbiere | 40 € e 2 appuntamenti | mensile |
| Risparmio personale | minimo 420 € | mensile |

Obiettivo annuale: accantonare almeno 5.000 €.

## Invarianti Contabili Da Testare

1. **Ogni riga ha un solo tipo**, e la somma per tipo ridà il totale lordo.
2. Importi convertiti in `Decimal(str(x))` appena letti da Notion; arrotondamento `ROUND_HALF_UP`.
3. Totali calcolati dal registro delle transazioni, mai sommando i risultati delle regole: le
   regole sovrapposte (DeepSeek dentro AI) non producono doppi conteggi.
4. I trasferimenti interni non entrano nelle spese effettive.
5. Righe non classificate o ambigue mostrate nel report, mai scartate in silenzio.
6. Errore o indisponibilita di Notion → stato `UNKNOWN`, mai `OK`.
7. Confini di periodo: date Notion trattate come date locali `Europe/Rome`; l'ultimo giorno del
   mese e incluso.
8. Stesso input → stesso output.

### Esempio Di Riconciliazione (Numeri Inventati)

Il test di regressione principale verifica che il report si riconcili con i totali lordi:

```
Uscite lorde 3.540,00 = trasferimenti 1.800,00 + spese effettive 1.650,00
                        + poker 50,00 + rettifica 40,00
Entrate lorde 3.700,00 = trasferimenti 1.800,00 + entrate effettive 1.900,00
```

Esito atteso delle regole sullo stesso mese inventato: cibo fuori 180,00/150 ❌, casa e
abbigliamento 120,00/150 ✅, delivery 3/2 ❌, AI e abbonamenti 55,00/70 ✅, DeepSeek 12,00/10 ❌,
barbiere 1/2 visite ✅ (20,00/40 ✅), rettifica 40,00 ⚠️. La fixture deve mescolare regole
rispettate e violate, trasferimenti a due righe e transazioni con piu categorie.

**Niente dati finanziari reali nel repository**, anche se privato: ne documenti ne fixture. Le
fixture in `tests/fixtures/` sono sintetiche. L'utente ha un'analisi reale di novembre 2026 che si
riconcilia; puo servire a verificare a mano l'output di `scripts/month_check.py`, ma resta fuori
dal repo.

## Domande Aperte

Da chiudere prima del task 2 del piano (le prime tre bloccano la classificazione delle righe):

1. **Classificazione fine**: tag a parole chiave in configurazione, nuove categorie in Notion
   (es. `Delivery`, `Barbiere`, `AI Services`), o entrambe? Le categorie Notion verrebbero gia
   usate dal bot via LLM in scrittura.
2. **Risparmio**: quali conti sono "di risparmio" (`Risparmio`? `Trade Republic`?). I 420 €/mese
   sono l'entrata netta su quei conti nel mese (entrate − prelievi)?
3. **Poker e rettifiche**: come sono registrati oggi in Notion? Conto dedicato, categoria, o solo
   il `Name`?
4. **Rimborsi**: riducono la spesa della categoria originale, o restano entrate (comportamento
   attuale dopo il commit `2913469`)?
5. **Hosting**: riaprire ora la scelta Lambda o rimandarla a quando servono notifiche programmate
   e Mini App? Vedi [`hosting-feasibility.md`](hosting-feasibility.md): niente filesystem
   persistente, e il limite di 250 MB va risolto comunque.
6. **Stato persistente per Phase 2–3**: deduplica delle notifiche e raccomandazioni accettate
   richiedono storage. Dove: DynamoDB (se Lambda), una pagina/DB Notion dedicato, o SQLite (se VM)?
7. **Abbonamenti**: verificare lo schema reale del DB `Subscriptions` (Pricing, Billing frequency,
   Renewal date, Type, Account) prima di leggerlo.

## Piano Incrementale

**Phase 1: motore e Telegram**

1. `NotionGateway.query_transactions(start, end)`: lettura paginata, testata con client finto.
2. `analysis/ledger.py`: assegnazione del tipo + test di partizione con fixture sintetica.
3. `analysis/rules.py`: tre tipi di regola, stati, caricamento della configurazione TOML.
4. `scripts/month_check.py --month 2026-11` + target `make`: stampa lo stato delle regole del mese,
   da confrontare a mano con l'analisi reale dell'utente. Legge Notion reale, non scrive.
5. Comandi Telegram `/budget` e `/report [YYYY-MM]`.
6. Riga di stato delle regole toccate dopo ogni salvataggio.

**Phase 2: monitoraggio proattivo** (dopo la decisione sull'hosting)

7. Lettura del DB `Subscriptions` e avvisi di rinnovo.
8. Notifiche programmate con deduplica sui cambi di stato.

**Phase 3: consulente AI**

9. Report discorsivo dell'LLM a partire da `MonthReport` (solo aggregati).
10. Raccomandazioni persistenti: proposta → accettata → regola attiva → misura dell'effetto.

**Phase 4: Telegram Mini App**

11. Endpoint JSON autenticato con `initData` + pagina con grafici (budget, categorie, storico).
