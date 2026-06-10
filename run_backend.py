import uvicorn

from app.runtime_config import load_runtime_config


def main():
    cfg = load_runtime_config()
    uvicorn.run("app.api:app", host=cfg.backend_host, port=cfg.backend_port, reload=False)


if __name__ == "__main__":
    main()

