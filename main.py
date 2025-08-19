# main.py
import logging

from app.notion_gateway import NotionGateway
from app.taxonomy import set_taxonomy
from app.telegram_bot import build_application

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    gw = NotionGateway()
    gw.verify_schema()  # tipi base
    set_taxonomy(gw.read_taxonomy())
    app = build_application()
    app.run_polling()


if __name__ == "__main__":
    main()
