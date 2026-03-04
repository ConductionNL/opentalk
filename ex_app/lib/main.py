"""OpenTalk ExApp - Nextcloud External Application wrapper for OpenTalk video conferencing.

OpenTalk is a secure video conferencing solution.
See: https://docs.opentalk.eu/
"""

import asyncio
import logging
import os
import subprocess
import threading
import typing
from contextlib import asynccontextmanager

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from nc_py_api import NextcloudApp
from nc_py_api.ex_app import (
    nc_app,
    run_app,
    setup_nextcloud_logging,
)
from nc_py_api.ex_app.integration_fastapi import AppAPIAuthMiddleware


# -- Logging -----------------------------------------------------------------
logging.basicConfig(
    level=logging.WARNING,
    format="[%(funcName)s]: %(message)s",
    datefmt="%H:%M:%S",
)
LOGGER = logging.getLogger("opentalk")
LOGGER.setLevel(logging.DEBUG)


# -- Configuration -----------------------------------------------------------
APP_ID = os.environ.get("APP_ID", "opentalk")
OPENTALK_PORT = int(os.environ.get("OPENTALK_PORT", "11311"))
OPENTALK_URL = f"http://localhost:{OPENTALK_PORT}"
OPENTALK_PROCESS = None

# Keycloak/OIDC configuration
KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "commonground")
KEYCLOAK_CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID", "opentalk")
KEYCLOAK_CLIENT_SECRET = os.environ.get("KEYCLOAK_CLIENT_SECRET", "")


# -- OpenTalk Process Management ---------------------------------------------
def get_oidc_env() -> dict:
    """Get OIDC environment variables for OpenTalk if Keycloak is configured."""
    if not KEYCLOAK_URL:
        return {}

    oidc_url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
    return {
        "OPENTALK_CTRL_OIDC__AUTHORITY": oidc_url,
        "OPENTALK_CTRL_OIDC__CLIENT_ID": KEYCLOAK_CLIENT_ID,
        "OPENTALK_CTRL_OIDC__CLIENT_SECRET": KEYCLOAK_CLIENT_SECRET,
    }


def start_opentalk() -> None:
    """Start the OpenTalk controller subprocess."""
    global OPENTALK_PROCESS

    if OPENTALK_PROCESS is not None and OPENTALK_PROCESS.poll() is None:
        return

    env = os.environ.copy()

    # Add OIDC configuration if Keycloak is configured
    env.update(get_oidc_env())
    if KEYCLOAK_URL:
        LOGGER.info("OIDC configured with Keycloak at %s", KEYCLOAK_URL)

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


def stop_opentalk() -> None:
    """Stop the OpenTalk controller subprocess."""
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
                    f"{OPENTALK_URL}/v1/",
                    timeout=5,
                )
                # Any of these statuses means the controller is running
                if resp.status_code in (200, 401, 404):
                    return True
        except Exception:
            pass
        await asyncio.sleep(1)
    return False


# -- Lifespan ----------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan handler."""
    setup_nextcloud_logging("opentalk", logging_level=logging.WARNING)
    LOGGER.info("Starting OpenTalk ExApp")
    start_opentalk()
    yield
    stop_opentalk()
    LOGGER.info("OpenTalk ExApp shutdown complete")


# -- FastAPI App -------------------------------------------------------------
APP = FastAPI(lifespan=lifespan)
APP.add_middleware(AppAPIAuthMiddleware)


# -- Enabled Handler ---------------------------------------------------------
def enabled_handler(enabled: bool, nc: NextcloudApp) -> str:
    """Handle app enable/disable events."""
    if enabled:
        LOGGER.info("Enabling OpenTalk ExApp")
        start_opentalk()
    else:
        LOGGER.info("Disabling OpenTalk ExApp")
        stop_opentalk()
    return ""


# -- Required Endpoints ------------------------------------------------------
@APP.get("/heartbeat")
async def heartbeat_callback():
    """Heartbeat endpoint for AppAPI health checks."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{OPENTALK_URL}/v1/",
                timeout=5,
            )
            if resp.status_code in (200, 401, 404):
                return JSONResponse(content={"status": "ok"})
    except Exception:
        pass
    return JSONResponse(content={"status": "error"}, status_code=503)


@APP.post("/init")
async def init_callback(
    b_tasks: BackgroundTasks,
    nc: typing.Annotated[NextcloudApp, Depends(nc_app)],
):
    """Initialization endpoint called by AppAPI after installation."""
    b_tasks.add_task(init_opentalk_task, nc)
    return JSONResponse(content={})


@APP.put("/enabled")
def enabled_callback(
    enabled: bool,
    nc: typing.Annotated[NextcloudApp, Depends(nc_app)],
):
    """Enable/disable callback from AppAPI."""
    return JSONResponse(content={"error": enabled_handler(enabled, nc)})


async def init_opentalk_task(nc: NextcloudApp):
    """Background task for OpenTalk initialization with progress reporting."""
    nc.set_init_status(0)
    LOGGER.info("Starting OpenTalk initialization...")

    start_opentalk()
    nc.set_init_status(20)

    nc.set_init_status(50)
    if await wait_for_opentalk():
        nc.set_init_status(100)
        LOGGER.info("OpenTalk initialization complete")
    else:
        LOGGER.error("OpenTalk failed to start within timeout")


# -- Catch-All Proxy ---------------------------------------------------------
@APP.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
async def proxy(request: Request, path: str):
    """Proxy all requests to OpenTalk controller."""
    try:
        async with httpx.AsyncClient() as client:
            url = f"{OPENTALK_URL}/{path}"

            headers = {
                k: v
                for k, v in request.headers.items()
                if k.lower()
                not in (
                    "host",
                    "connection",
                    "transfer-encoding",
                    "accept-encoding",
                    "content-length",
                )
            }

            resp = await client.request(
                method=request.method,
                url=url,
                content=await request.body(),
                headers=headers,
                params=request.query_params,
                timeout=60,
            )

            resp_headers = {
                k: v
                for k, v in resp.headers.items()
                if k.lower()
                not in (
                    "content-encoding",
                    "transfer-encoding",
                    "content-length",
                )
            }

            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers=resp_headers,
            )
    except httpx.RequestError as e:
        LOGGER.error("Proxy error: %s", str(e))
        return JSONResponse(
            {"error": f"Proxy error: {str(e)}"},
            status_code=502,
        )


# -- Entry Point -------------------------------------------------------------
if __name__ == "__main__":
    run_app(APP, log_level="info")
