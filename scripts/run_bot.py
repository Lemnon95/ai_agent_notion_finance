#!/usr/bin/env python3
from __future__ import annotations

import logging

from app.telegram_bot import build_application  # aggiorna path se diverso

logging.basicConfig(level=logging.INFO)


def main() -> None:
    app = build_application()
    print("Bot in polling…")
    # run_polling è SINCRONO in PTB 21
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
