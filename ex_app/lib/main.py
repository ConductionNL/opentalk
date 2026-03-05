"""OpenTalk ExApp - Nextcloud External Application wrapper for OpenTalk video conferencing."""

import asyncio
import logging
import os
import subprocess
import threading
import typing
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from nc_py_api import NextcloudApp
from nc_py_api.ex_app import nc_app, run_app, setup_nextcloud_logging
from nc_py_api.ex_app.integration_fastapi import AppAPIAuthMiddleware


# ── Logging ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="[%(funcName)s]: %(message)s",
    datefmt="%H:%M:%S",
)
LOGGER = logging.getLogger("opentalk")
LOGGER.setLevel(logging.DEBUG)


# ── Configuration ───────────────────────────────────────────────────
APP_ID = os.environ.get("APP_ID", "opentalk")
OPENTALK_PORT = int(os.environ.get("OPENTALK_PORT", "11311"))
OPENTALK_PROCESS = None

# Detect HaRP mode and set proxy prefix accordingly
HARP_ENABLED = bool(os.environ.get("HP_SHARED_KEY"))
if HARP_ENABLED:
    PROXY_PREFIX = f"/exapps/{APP_ID}"
else:
    PROXY_PREFIX = f"/index.php/apps/app_api/proxy/{APP_ID}"


# ── Process Management ─────────────────────────────────────────────
def start_opentalk():
    """Start the OpenTalk controller service."""
    global OPENTALK_PROCESS
    if OPENTALK_PROCESS is not None and OPENTALK_PROCESS.poll() is None:
        return

    env = os.environ.copy()
    OPENTALK_PROCESS = subprocess.Popen(
        ["/usr/local/bin/opentalk-controller"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    def log_output():
        for line in OPENTALK_PROCESS.stdout:
            LOGGER.info("[opentalk] %s", line.decode().strip())

    threading.Thread(target=log_output, daemon=True).start()
    LOGGER.info("OpenTalk controller started with PID: %d", OPENTALK_PROCESS.pid)


def stop_opentalk():
    """Stop the OpenTalk controller service."""
    global OPENTALK_PROCESS
    if OPENTALK_PROCESS is not None:
        OPENTALK_PROCESS.terminate()
        try:
            OPENTALK_PROCESS.wait(timeout=30)
        except subprocess.TimeoutExpired:
            OPENTALK_PROCESS.kill()
        OPENTALK_PROCESS = None
        LOGGER.info("OpenTalk controller stopped")


async def wait_for_opentalk(timeout: int = 90) -> bool:
    """Wait for OpenTalk controller to become healthy."""
    for _ in range(timeout):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"http://localhost:{OPENTALK_PORT}/v1/",
                    timeout=2,
                )
                if resp.status_code in (200, 401, 404):
                    return True
        except Exception:
            pass
        await asyncio.sleep(1)
    return False


# ── Lifespan ────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_nextcloud_logging("opentalk", logging_level=logging.WARNING)
    LOGGER.info("Starting OpenTalk ExApp")
    yield
    stop_opentalk()
    LOGGER.info("OpenTalk ExApp shutdown complete")


# ── FastAPI App ─────────────────────────────────────────────────────
APP = FastAPI(lifespan=lifespan)
APP.add_middleware(AppAPIAuthMiddleware)


# ── Inline iframe loader JS ────────────────────────────────────────
IFRAME_LOADER_JS = f"""
(function() {{
    var style = document.createElement('style');
    style.textContent =
        '#content.app-app_api {{' +
        '  margin-top: var(--header-height) !important;' +
        '  height: var(--body-height) !important;' +
        '  width: calc(100% - var(--body-container-margin) * 2) !important;' +
        '  border-radius: var(--body-container-radius) !important;' +
        '  overflow: hidden !important;' +
        '  padding: 0 !important;' +
        '}}' +
        '#content.app-app_api > iframe {{ width: 100%; height: 100%; border: none; display: block; }}';
    document.head.appendChild(style);

    function setup() {{
        var content = document.getElementById('content');
        if (!content) return;
        content.innerHTML = '';
        var iframe = document.createElement('iframe');
        iframe.src = '{PROXY_PREFIX}/';
        iframe.allow = 'camera; microphone; clipboard-read; clipboard-write; display-capture';
        content.appendChild(iframe);
    }}

    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', setup);
    }} else {{
        setup();
    }}
}})();
""".strip()


@APP.get("/js/opentalk-iframe-loader.js")
async def iframe_loader():
    """Serve the inline iframe loader script."""
    return Response(
        content=IFRAME_LOADER_JS,
        media_type="application/javascript",
    )


# ── Enabled Handler ────────────────────────────────────────────────
def enabled_handler(enabled: bool, nc: NextcloudApp) -> str:
    """Handle app enable/disable events."""
    if enabled:
        LOGGER.info("Enabling OpenTalk ExApp")
        nc.ui.resources.set_script("top_menu", "opentalk", "js/opentalk-iframe-loader")
        nc.ui.top_menu.register("opentalk", "OpenTalk", "img/app.svg", True)
        start_opentalk()
    else:
        LOGGER.info("Disabling OpenTalk ExApp")
        nc.ui.resources.delete_script("top_menu", "opentalk", "js/opentalk-iframe-loader")
        nc.ui.top_menu.unregister("opentalk")
        stop_opentalk()
    return ""


# ── Required Endpoints ──────────────────────────────────────────────
@APP.get("/heartbeat")
async def heartbeat():
    """Heartbeat endpoint for AppAPI health checks."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"http://localhost:{OPENTALK_PORT}/v1/",
                timeout=5,
            )
            if resp.status_code in (200, 401, 404):
                return JSONResponse({"status": "ok"})
    except Exception:
        pass
    return JSONResponse({"status": "waiting"})


@APP.post("/init")
async def init_callback(
    b_tasks: BackgroundTasks,
    nc: typing.Annotated[NextcloudApp, Depends(nc_app)],
):
    """Initialization endpoint called by AppAPI after installation."""
    b_tasks.add_task(init_task, nc)
    return JSONResponse(content={})


@APP.put("/enabled")
def enabled_callback(
    enabled: bool,
    nc: typing.Annotated[NextcloudApp, Depends(nc_app)],
):
    """Enable/disable callback from AppAPI."""
    return JSONResponse(content={"error": enabled_handler(enabled, nc)})


async def init_task(nc: NextcloudApp):
    """Background task for OpenTalk initialization with progress reporting."""
    nc.set_init_status(0)
    LOGGER.info("Starting OpenTalk initialization...")

    start_opentalk()
    nc.set_init_status(20)

    if await wait_for_opentalk():
        nc.set_init_status(60)
        nc.ui.resources.set_script("top_menu", "opentalk", "js/opentalk-iframe-loader")
        nc.ui.top_menu.register("opentalk", "OpenTalk", "img/app.svg", True)
        nc.set_init_status(100)
        LOGGER.info("OpenTalk initialization complete")
    else:
        LOGGER.error("OpenTalk failed to start within timeout")


# ── Catch-All Proxy ────────────────────────────────────────────────
@APP.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
async def proxy(request: Request, path: str):
    """Proxy all requests to OpenTalk controller."""
    # Serve ex_app static files (icons, JS) directly from disk
    if path.startswith(("ex_app/", "img/")):
        file_path = Path(__file__).parent.parent.parent / path
        if file_path.is_file():
            from starlette.responses import FileResponse

            return FileResponse(str(file_path))

    try:
        async with httpx.AsyncClient() as client:
            url = f"http://localhost:{OPENTALK_PORT}/{path}"

            resp = await client.request(
                method=request.method,
                url=url,
                content=await request.body(),
                headers={
                    k: v
                    for k, v in request.headers.items()
                    if k.lower()
                    not in ("host", "connection", "transfer-encoding", "accept-encoding")
                },
                params=request.query_params,
                timeout=60,
            )

            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers={
                    k: v
                    for k, v in resp.headers.items()
                    if k.lower()
                    not in ("content-encoding", "transfer-encoding", "content-length")
                },
            )
    except httpx.RequestError as e:
        LOGGER.error("Proxy error: %s", str(e))
        return JSONResponse(
            {"error": f"Proxy error: {str(e)}"},
            status_code=502,
        )


# ── Entry Point ─────────────────────────────────────────────────────
if __name__ == "__main__":
    os.chdir(Path(__file__).parent)
    run_app(APP, log_level="info")
