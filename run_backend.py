"""Packaged backend entry point."""
import logging

from app_config import configure_logging


def main():
    values = configure_logging()
    logging.getLogger(__name__).info("后端启动")
    from websocket_backend.main import main as backend_main
    backend_main()


if __name__ == "__main__":
    main()

