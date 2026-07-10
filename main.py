import uvicorn

from app import create_app
from config import WORKSPACE, get_config, load_config
from logger import setup_logging


def main() -> None:
    cfg = get_config()
    application = create_app()
    uvicorn.run(
        application,
        host=cfg.system.listen_addr,
        port=cfg.system.listen_port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    load_config()
    setup_logging(level="INFO", file_path=WORKSPACE / "app.log")

    main()
