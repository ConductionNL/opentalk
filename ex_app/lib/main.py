"""
OpenTalk ExApp - FastAPI wrapper for Nextcloud AppAPI integration

OpenTalk is a secure video conferencing solution.
See: https://docs.opentalk.eu/
"""
import os
import subprocess
import asyncio
import base64
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse, Response

# Environment variables set by AppAPI
APP_ID = os.environ.get("APP_ID", "opentalk")
APP_VERSION = os.environ.get("APP_VERSION", "0.1.0")
APP_SECRET = os.environ.get("APP_SECRET", "")
APP_HOST = os.environ.get("APP_HOST", "0.0.0.0")
APP_PORT = int(os.environ.get("APP_PORT", "9000"))
NEXTCLOUD_URL = os.environ.get("NEXTCLOUD_URL", "http://nextcloud")

# OpenTalk configuration - controller runs on port 11311 by default
OPENTALK_PORT = int(os.environ.get("OPENTALK_PORT", "11311"))
OPENTALK_PROCESS = None

# Keycloak/OIDC configuration
KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "commonground")
KEYCLOAK_CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID", "opentalk")
KEYCLOAK_CLIENT_SECRET = os.environ.get("KEYCLOAK_CLIENT_SECRET", "")


def get_auth_header() -> dict:
    """Generate AppAPI authentication header"""
    auth = base64.b64encode(f":{APP_SECRET}".encode()).decode()
    return {
        "EX-APP-ID": APP_ID,
        "EX-APP-VERSION": APP_VERSION,
        "AUTHORIZATION-APP-API": auth,
    }


async def report_status(progress: int) -> None:
    """Report initialization progress to Nextcloud"""
    try:
        async with httpx.AsyncClient() as client:
            await client.put(
                f"{NEXTCLOUD_URL}/ocs/v1.php/apps/app_api/apps/status",
                headers=get_auth_header(),
                json={"progress": progress},
                timeout=10,
            )
    except Exception as e:
        print(f"Failed to report status: {e}")


def get_oidc_env() -> dict:
    """Get OIDC environment variables for OpenTalk if Keycloak is configured"""
    if not KEYCLOAK_URL:
        return {}

    oidc_url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
    return {
        # OpenTalk OIDC settings (uses OPENTALK_CTRL__ prefix)
        "OPENTALK_CTRL_OIDC__AUTHORITY": oidc_url,
        "OPENTALK_CTRL_OIDC__CLIENT_ID": KEYCLOAK_CLIENT_ID,
        "OPENTALK_CTRL_OIDC__CLIENT_SECRET": KEYCLOAK_CLIENT_SECRET,
    }


def start_opentalk() -> None:
    """Start the OpenTalk controller service"""
    global OPENTALK_PROCESS
    if OPENTALK_PROCESS is not None:
        return

    env = os.environ.copy()

    # Add OIDC configuration if Keycloak is configured
    env.update(get_oidc_env())
    if KEYCLOAK_URL:
        print(f"OIDC configured with Keycloak at {KEYCLOAK_URL}")

    # Start OpenTalk controller
    OPENTALK_PROCESS = subprocess.Popen(
        ["/usr/local/bin/opentalk-controller"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(f"OpenTalk controller started with PID: {OPENTALK_PROCESS.pid}")


def stop_opentalk() -> None:
    """Stop the OpenTalk controller service"""
    global OPENTALK_PROCESS
    if OPENTALK_PROCESS is not None:
        OPENTALK_PROCESS.terminate()
        try:
            OPENTALK_PROCESS.wait(timeout=30)
        except subprocess.TimeoutExpired:
            OPENTALK_PROCESS.kill()
        OPENTALK_PROCESS = None
        print("OpenTalk controller stopped")


async def wait_for_opentalk(timeout: int = 90) -> bool:
    """Wait for OpenTalk controller to become healthy"""
    for _ in range(timeout):
        try:
            async with httpx.AsyncClient() as client:
                # OpenTalk controller serves on /v1 endpoint
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    print(f"OpenTalk ExApp starting on {APP_HOST}:{APP_PORT}")
    yield
    stop_opentalk()
    print("OpenTalk ExApp shutdown complete")


app = FastAPI(lifespan=lifespan)


@app.get("/heartbeat")
async def heartbeat():
    """Health check endpoint for AppAPI"""
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
    return JSONResponse({"status": "error"}, status_code=503)


@app.post("/init")
async def init(background_tasks: BackgroundTasks):
    """Initialization endpoint called by AppAPI during deployment"""
    async def do_init():
        await report_status(0)
        print("Starting OpenTalk initialization...")

        await report_status(20)
        start_opentalk()

        await report_status(50)
        if await wait_for_opentalk():
            await report_status(100)
            print("OpenTalk initialization complete")
        else:
            print("OpenTalk failed to start - check configuration")
            await report_status(0)

    background_tasks.add_task(do_init)
    return JSONResponse({"status": "init_started"})


@app.put("/enabled")
async def enabled(request: Request):
    """Enable/disable endpoint called by AppAPI"""
    data = await request.json()
    is_enabled = data.get("enabled", False)

    if is_enabled:
        start_opentalk()
        await wait_for_opentalk(timeout=60)
    else:
        stop_opentalk()

    return JSONResponse({"status": "ok"})


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy(request: Request, path: str):
    """Proxy all other requests to OpenTalk controller"""
    try:
        async with httpx.AsyncClient() as client:
            url = f"http://localhost:{OPENTALK_PORT}/{path}"

            resp = await client.request(
                method=request.method,
                url=url,
                content=await request.body(),
                headers={
                    k: v for k, v in request.headers.items()
                    if k.lower() not in ("host", "content-length")
                },
                params=request.query_params,
                timeout=60,
            )

            return Response(
                content=resp.content,
                status_code=resp.status_code,
                headers={
                    k: v for k, v in resp.headers.items()
                    if k.lower() not in ("content-encoding", "transfer-encoding")
                },
            )
    except httpx.RequestError as e:
        return JSONResponse(
            {"error": f"Proxy error: {str(e)}"},
            status_code=502,
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)
