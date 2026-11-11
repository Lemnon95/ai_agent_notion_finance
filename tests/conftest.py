import os

# Valori finti per le impostazioni obbligatorie: i test non devono dipendere da un `.env` reale
# (in un ambiente pulito non esiste) e non fanno chiamate di rete.
for _name in ("TELEGRAM_BOT_TOKEN", "NOTION_TOKEN", "NOTION_DB_ID", "OPENAI_API_KEY"):
    os.environ.setdefault(_name, "test")
