import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles

from pasteup.routes.jobs import router as jobs_router
from pasteup.routes.ui import router as ui_router

APP_DIR = Path(__file__).resolve().parent

# The app reads and writes local paths and has no authentication, so it answers
# only requests addressed to this machine. Checking Host stops a web page whose
# domain has been re-pointed at 127.0.0.1 (DNS rebinding) from driving the app
# through the user's browser. Extra names, comma-separated, are for serving the
# app deliberately under another host.
ALLOWED_HOSTS_ENV_VAR = "IMAGE_GRID_ALLOWED_HOSTS"
DEFAULT_ALLOWED_HOSTS = ("localhost", "127.0.0.1", "[::1]")


def allowed_hosts() -> list[str]:
    extra_hosts = os.environ.get(ALLOWED_HOSTS_ENV_VAR, "").split(",")
    return [*DEFAULT_ALLOWED_HOSTS, *(host.strip() for host in extra_hosts if host.strip())]


app = FastAPI(title="Image Grid App")

app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts())
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

app.include_router(ui_router)
app.include_router(jobs_router, prefix="/api")
