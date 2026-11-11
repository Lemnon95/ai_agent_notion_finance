# Studio Di Fattibilita: Hosting Del Bot Sempre Acceso

**Data:** 2026-11-11
**Stato:** studio concluso, **non implementato**. Nessuna modifica al codice e nessuna risorsa cloud
creata. Prezzi e piani gratuiti cambiano spesso: riverificarli prima di implementare.

## Problema

Il bot gira con `make bot` sul PC dell'utente, in modalita polling. A PC spento non registra
nulla, e capita spesso. Telegram conserva i messaggi non letti solo 24 ore, poi vanno persi.

## Vincoli

- Budget: **sotto 0,50 € al mese**.
- Nessun dispositivo sempre acceso in casa (Raspberry Pi, NAS, vecchio PC).
- Account AWS gia esistente, creato nel 2022: il vecchio free tier di 12 mesi (EC2 gratuito) e
  scaduto da tempo.
- Preferenza dell'utente: **AWS Lambda** (niente nuovo fornitore) piuttosto che una VM Oracle
  (niente modifiche al codice).

## Opzioni Valutate

| Opzione | Costo a regime | Modifiche al codice | Esito |
|---|---|---|---|
| Google Cloud e2-micro (VM) | ~3,65 $/mese per l'IPv4 pubblico | nessuna | scartata: fuori budget |
| AWS EC2 (VM) | qualche €/mese (VM + IPv4) | nessuna | scartata: fuori budget |
| Oracle Cloud Always Free (VM) | 0 € | nessuna | valida; rischio di recupero per inattivita (CPU, rete e memoria sotto il 20% per 7 giorni), evitabile passando a Pay As You Go; serve un nuovo account con carta |
| Google Cloud Run (webhook) | 0 € (piano gratuito) | webhook + stato persistente | valida |
| **AWS Lambda (webhook)** | 0 € (piano gratuito permanente) | webhook + stato persistente | **preferita dall'utente** |

Il polling non richiede che il bot sia raggiungibile da internet. Il webhook (Lambda, Cloud Run)
invece si: Telegram chiama un URL HTTPS a ogni messaggio.

## Analisi Di AWS Lambda

### Ostacolo principale: dimensione del pacchetto

Un pacchetto Lambda zip puo occupare al massimo **250 MB scompattato**. Le sole dipendenze runtime
(`requirements.txt`), installate per Lambda Python 3.12 arm64, occupano **298 MB**:

- `litellm`: 159 MB, di cui `litellm/proxy` 59 MB, non usato dal bot;
- `botocore` 31 MB + `boto3` 1,6 MB, gia forniti dal runtime Lambda;
- `openai` 20 MB; il resto e piccolo.

Misura fatta con:

```bash
pip install --target <dir> --platform manylinux_2_34_aarch64 --platform manylinux_2_28_aarch64 \
  --platform manylinux2014_aarch64 --implementation cp --python-version 3.12 \
  --only-binary=:all: -r requirements.txt
```

`hf-xet` non ha una build `manylinux2014_aarch64`; servono i tag piu recenti. Lambda Python 3.12
gira su Amazon Linux 2023 (glibc 2.34).

Modi per superare il limite:

1. Escludere `boto3`/`botocore`: circa 265 MB, **non basta** da solo.
2. Escludere anche le parti inutilizzate di litellm (`proxy`): circa 205 MB. Funziona ma e
   fragile: va ricontrollato a ogni aggiornamento di litellm.
3. Immagine container (limite 10 GB): serve Docker per costruirla (non presente nell'ambiente
   attuale); lo spazio su ECR costa qualche centesimo al mese.
4. **Sostituire litellm con l'SDK ufficiale `openai`** (Groq espone un'API compatibile OpenAI):
   pacchetto molto piu piccolo e avvio a freddo piu rapido. Richiede di riscrivere la chiamata
   in `app/llm.py` e si perde l'astrazione multi-provider di litellm. **Strada consigliata.**

### Lavoro sul codice necessario

- Modalita webhook per Lambda (handler che riceve l'update Telegram dalla Function URL),
  mantenendo il polling (`make bot`) per lo sviluppo locale.
- Verifica dell'header `X-Telegram-Bot-Api-Secret-Token` sulle richieste in arrivo.
- Stato su DynamoDB invece che in memoria: anti-duplicati (`IdempotencyStore`) e ultima
  registrazione per `/annulla`. Effetto positivo: sopravvivono ai riavvii.
- Controllo dello spegnimento del modello (`check_model_shutdown()`) al massimo una volta al
  giorno, salvando la data dell'ultimo controllo, invece che a ogni avvio a freddo.
- Bootstrap (schema e tassonomia Notion) a ogni avvio a freddo: aggiunge latenza al primo
  messaggio dopo una pausa.

### Costi stimati

- Lambda: piano gratuito permanente (le fonti indicano 1 milione di richieste al mese; da
  confermare sulla pagina ufficiale). Il volume del bot e di pochi messaggi al giorno.
- DynamoDB: usare la capacita *provisioned* minima, coperta dal piano gratuito permanente. La
  modalita *on-demand* si paga a richiesta (pochi centesimi, ma non zero).
- CloudWatch Logs: quota gratuita ampia per questo volume.
- ECR, solo con l'opzione container: qualche centesimo al mese.

### Deploy

Nell'ambiente di sviluppo attuale non ci sono AWS CLI, SAM, Docker ne credenziali AWS: il deploy
va fatto dall'utente dal proprio terminale, con comandi o script preparati nel repository.

## Prossimi Passi, Se Si Riprende

1. Decidere se sostituire litellm con l'SDK `openai` (opzione 4).
2. Pianificare in plan mode: handler webhook, stato su DynamoDB, packaging, script di deploy.
3. Riverificare piani gratuiti e prezzi di Lambda, DynamoDB e CloudWatch.

## Fonti

- [AWS Billing – AWS Free Tier](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html)
- [The $0 AWS account in 2026 (AWS Builder)](https://builder.aws.com/content/3Kkt4kNiDSUnO3n6db2weSNubzE/the-dollar0-aws-account-in-2026-free-plan-credits-guardrails)
- [AWS Free Tier 2026 (AgentDeals)](https://agentdeals.dev/aws-free-tier-2026)
- [GCP e2-micro e costo dell'IPv4 (Yangworks)](https://yangworks.dev/guides/google-cloud-free-tier-e2-micro)
- [Cloud Run pricing](https://cloud.google.com/run/pricing)
- [Oracle – Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm)
- [Oracle Always Free: limiti e recupero per inattivita (inithtml)](https://en.inithtml.com/resources/oracle-cloud-free-tier-review-after-real-world-use-truly-free-but-is-it-worth-it/)
