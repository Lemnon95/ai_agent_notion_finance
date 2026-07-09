# Notion Finance Schema

Questa pagina documenta lo schema Notion usato dal bot Telegram finance.

## Pagina Finance

La pagina `Finance` contiene i database principali:

- `Transactions`: database delle transazioni salvate dal bot.
- `Outcome`: categorie di uscita.
- `Income`: categorie di entrata.
- `Accounts`: conti/strumenti finanziari.
- `Months`: riepiloghi mensili usati da Notion.

## Transactions

Proprieta richieste dal codice:

- `Name`: `title`
- `Amount`: `number`, formato euro
- `Date`: `date`
- `Account`: `relation` verso `Accounts`
- `Outcome`: `relation` verso `Outcome`
- `Income`: `relation` verso `Income`
- `Notes`: `text`, opzionale ma supportata dal bot

Regole applicative:

- Una transazione deve avere `Account`.
- Una transazione deve avere `Outcome` oppure `Income`, mai entrambe.
- Il bot salva importi positivi; il significato entrata/uscita deriva dalla relation.
- I titoli delle pagine collegate sono la tassonomia runtime del bot.

## Accounts

Il bot legge i titoli dalla property `Name`. Al momento la tassonomia reale include:

- `Trade Republic`
- `Revolut`
- `Risparmio`
- `Poste Italiane`
- `Contanti`
- `Hype`

## Outcome

Esempi di categorie reali:

- Macro: `Wants`, `Needs`, `Savings`
- Specifiche: `Supermarket`, `Eating Out and Takeway`, `Bollette`, `Travel`, `Fun`,
  `Gifts & Donations`, `Prelievo`, `Risparmio`, `Other Outcome`

Il bot puo salvare una o due categorie outcome. Per le spese ordinarie preferisce
`[MACRO, SPECIFICA]`, ad esempio `["Needs", "Supermarket"]`.

## Income

Esempi di categorie reali:

- `Salary`
- `Gifts`
- `Prelievo`
- `Risparmio`
- `Other Income`

Il bot salva una sola categoria income.

## Trasferimenti

Notion rappresenta spesso un trasferimento tra account con due righe nello stesso database:

- riga `Outcome` sull'account di origine;
- riga `Income` sull'account di destinazione.

Esempio: `prelievo 100 euro da Hype`

- `Hype`, `Outcome = Prelievo`, `Amount = 100`
- `Contanti`, `Income = Prelievo`, `Amount = 100`

Il bot crea automaticamente due righe solo quando origine e destinazione sono chiare. Per frasi
ambigue crea una singola riga o passa al parser LLM.

## Note Per Sviluppo

- Non hardcodare la tassonomia come fonte di verita: leggerla da Notion.
- Se si rinominano property Notion, aggiornare `app/notion_gateway.py`.
- Se si aggiungono categorie, aggiornare eventualmente prompt e normalizzatore solo per migliorare
  il mapping; la validazione deve continuare a dipendere dalla tassonomia runtime.
- `Risparmio Car` non e una categoria attuale: usare `Risparmio`.
