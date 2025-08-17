import logging

from app.telegram_bot import build_application

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    application = build_application()
    # Polling per sviluppo locale
    application.run_polling(drop_pending_updates=True, allowed_updates=None)
