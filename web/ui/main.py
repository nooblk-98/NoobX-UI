from uuid import uuid4

from .constants import CONFIG_PATH, DEFAULTS
from .routes import create_app
from .store import _load_store, _save_store, build_config, write_config
from .system import ensure_dirs, ensure_certs
from .xray_core import start_xray


def bootstrap() -> None:
    ensure_dirs()
    store = _load_store()
    if not store.get("configs"):
        default_item = dict(DEFAULTS)
        default_item["id"] = str(uuid4())
        default_item["enabled"] = True
        store["configs"] = [default_item]
        _save_store(store)

    if not CONFIG_PATH.exists():
        for c in store.get("configs", []):
            ensure_certs(c["domain"])
        write_config(build_config(store.get("configs", [])))
    start_xray()


def get_app():
    return create_app()
