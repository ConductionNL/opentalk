"""OpenTalk ExApp - Nextcloud External Application wrapper for OpenTalk video conferencing."""

import asyncio
import logging
import os
import selectors
import socket
import subprocess
import threading
import typing
from contextlib import asynccontextmanager
from pathlib import Path

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
OPENTALK_PORT = int(os.environ.get("OPENTALK_PORT", "11311"))
OPENTALK_URL = f"http://localhost:{OPENTALK_PORT}"
OPENTALK_PROCESS = None

APP_ID = os.environ.get("APP_ID", "opentalk")
HARP_ENABLED = bool(os.environ.get("HP_SHARED_KEY"))
if HARP_ENABLED:
    PROXY_PREFIX = f"/exapps/{APP_ID}"
else:
    PROXY_PREFIX = f"/index.php/apps/app_api/proxy/{APP_ID}"

# Keycloak/OIDC configuration
KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "commonground")
KEYCLOAK_CLIENT_ID = os.environ.get("KEYCLOAK_CLIENT_ID", "opentalk-controller")
KEYCLOAK_CLIENT_SECRET = os.environ.get("KEYCLOAK_CLIENT_SECRET", "opentalk-secret")

# Keycloak ExApp token API (for server-side auth)
KEYCLOAK_EXAPP_URL = os.environ.get(
    "KEYCLOAK_EXAPP_URL", "http://openregister-exapp-keycloak:23002"
)
# AppAPI auth for ExApp-to-ExApp communication
NEXTCLOUD_URL = os.environ.get("NEXTCLOUD_URL", "http://nextcloud")
APP_SECRET = os.environ.get("APP_SECRET", "")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")


# -- Local Port Proxy --------------------------------------------------------
KEYCLOAK_LOCAL_PORT = int(os.environ.get("KEYCLOAK_LOCAL_PORT", "8180"))
KEYCLOAK_INTERNAL_HOST = os.environ.get(
    "KEYCLOAK_INTERNAL_HOST", "openregister-exapp-keycloak"
)
KEYCLOAK_INTERNAL_PORT = int(os.environ.get("KEYCLOAK_INTERNAL_PORT", "8080"))


def _tcp_proxy_thread() -> None:
    """Forward localhost:KEYCLOAK_LOCAL_PORT -> KEYCLOAK_INTERNAL_HOST:KEYCLOAK_INTERNAL_PORT."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", KEYCLOAK_LOCAL_PORT))
    srv.listen(32)
    srv.setblocking(False)
    sel = selectors.DefaultSelector()
    sel.register(srv, selectors.EVENT_READ)

    def _accept(sock: socket.socket) -> None:
        client, _ = sock.accept()
        client.setblocking(False)
        try:
            upstream = socket.create_connection(
                (KEYCLOAK_INTERNAL_HOST, KEYCLOAK_INTERNAL_PORT), timeout=5
            )
            upstream.setblocking(False)
        except OSError:
            client.close()
            return
        sel.register(client, selectors.EVENT_READ, upstream)
        sel.register(upstream, selectors.EVENT_READ, client)

    while True:
        for key, _ in sel.select(timeout=1):
            if key.fileobj is srv:
                _accept(key.fileobj)
            else:
                data = None
                try:
                    data = key.fileobj.recv(65536)
                except OSError:
                    pass
                if data:
                    try:
                        key.data.sendall(data)
                    except OSError:
                        data = None
                if not data:
                    sel.unregister(key.fileobj)
                    sel.unregister(key.data)
                    key.fileobj.close()
                    key.data.close()


def start_keycloak_proxy() -> None:
    """Start the local TCP proxy for Keycloak in a daemon thread."""
    threading.Thread(target=_tcp_proxy_thread, daemon=True).start()
    LOGGER.info(
        "Keycloak proxy: localhost:%d -> %s:%d",
        KEYCLOAK_LOCAL_PORT,
        KEYCLOAK_INTERNAL_HOST,
        KEYCLOAK_INTERNAL_PORT,
    )


# -- OpenTalk Process Management ---------------------------------------------
def get_oidc_env() -> dict:
    """Get OIDC environment variables for OpenTalk via local Keycloak proxy.

    Only override the authority URL — the controller.toml already has the correct
    client_id and client_secret for both frontend and controller sections.
    Setting OPENTALK_CTRL_OIDC__CLIENT_ID would override oidc.client_id (top-level)
    and potentially break the controller's introspection which uses oidc.controller.client_id.
    """
    oidc_url = f"http://localhost:{KEYCLOAK_LOCAL_PORT}/realms/{KEYCLOAK_REALM}"
    return {
        "OPENTALK_CTRL_OIDC__AUTHORITY": oidc_url,
    }


def start_opentalk() -> None:
    """Start the OpenTalk controller service."""
    global OPENTALK_PROCESS

    if OPENTALK_PROCESS is not None and OPENTALK_PROCESS.poll() is None:
        return

    env = os.environ.copy()
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
                    f"{OPENTALK_URL}/v1/",
                    timeout=2,
                )
                if resp.status_code in (200, 401, 404):
                    return True
        except Exception:
            pass
        await asyncio.sleep(1)
    return False


# -- Frontend Path Rewriting (on-disk, at startup) --------------------------
FRONTEND_DIR = Path("/app/frontend")


def rewrite_frontend_paths() -> None:
    """Rewrite hardcoded absolute paths in frontend files to use proxy prefix."""
    if not FRONTEND_DIR.is_dir():
        LOGGER.warning("Frontend directory %s not found, skipping path rewrite", FRONTEND_DIR)
        return

    marker = FRONTEND_DIR / ".paths_rewritten"
    if marker.exists() and marker.read_text().strip() == PROXY_PREFIX:
        LOGGER.info("Frontend paths already rewritten for prefix %s", PROXY_PREFIX)
        return

    LOGGER.info("Rewriting frontend paths for proxy prefix: %s", PROXY_PREFIX)

    # Rewrite index.html
    index_path = FRONTEND_DIR / "index.html"
    if index_path.is_file():
        content = index_path.read_text()
        for prefix in ["/assets/", "/fonts.", "/fonts/", "/favicon", "/config.js",
                        "/manifest.json", "/tflite/", "/locales/"]:
            content = content.replace(f'"{prefix}', f'"{PROXY_PREFIX}{prefix}')
            content = content.replace(f"'{prefix}", f"'{PROXY_PREFIX}{prefix}")
            content = content.replace(f"({prefix}", f"({PROXY_PREFIX}{prefix}")
        index_path.write_text(content)

    # Rewrite JS bundles in assets/
    assets_dir = FRONTEND_DIR / "assets"
    if assets_dir.is_dir():
        for js_file in assets_dir.glob("*.js"):
            content = js_file.read_text(errors="replace")
            original = content
            content = content.replace(
                "${window.location.host}/locales/",
                f"${{window.location.host}}{PROXY_PREFIX}/locales/",
            )
            content = content.replace('"/locales/', f'"{PROXY_PREFIX}/locales/')
            content = content.replace("url('/assets/", f"url('{PROXY_PREFIX}/assets/")
            content = content.replace('url("/assets/', f'url("{PROXY_PREFIX}/assets/')
            if content != original:
                js_file.write_text(content)
                LOGGER.info("Rewrote paths in %s", js_file.name)

    marker.write_text(PROXY_PREFIX)
    LOGGER.info("Frontend path rewriting complete")


# -- Lifespan ----------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_nextcloud_logging("opentalk", logging_level=logging.WARNING)
    LOGGER.info("Starting OpenTalk ExApp")
    rewrite_frontend_paths()
    start_keycloak_proxy()
    start_opentalk()
    yield
    stop_opentalk()
    LOGGER.info("OpenTalk ExApp shutdown complete")


# -- FastAPI App -------------------------------------------------------------
APP = FastAPI(lifespan=lifespan)
APP.add_middleware(AppAPIAuthMiddleware)


# -- Iframe Loader JS --------------------------------------------------------
# Loads OpenTalk in an iframe. The frontend inside the iframe will call
# /api/auth/token to get a pre-authenticated Keycloak token, avoiding
# any browser-side OIDC redirect that CSP would block.
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
        headers={"Cache-Control": "no-cache, no-store"},
    )


# -- Enabled Handler ---------------------------------------------------------
def enabled_handler(enabled: bool, nc: NextcloudApp) -> str:
    """Handle app enable/disable events."""
    if enabled:
        LOGGER.info("Enabling OpenTalk ExApp")
        nc.ui.resources.set_script("top_menu", "opentalk", "js/opentalk-iframe-loader")
        nc.ui.top_menu.register("opentalk", "OpenTalk", "ex_app/img/app.svg", True)
        start_opentalk()
    else:
        LOGGER.info("Disabling OpenTalk ExApp")
        nc.ui.resources.delete_script("top_menu", "opentalk", "js/opentalk-iframe-loader")
        nc.ui.top_menu.unregister("opentalk")
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
                return JSONResponse({"status": "ok"})
    except Exception:
        pass
    return JSONResponse({"status": "ok"})


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

    if await wait_for_opentalk():
        nc.set_init_status(60)
        nc.ui.resources.set_script("top_menu", "opentalk", "js/opentalk-iframe-loader")
        nc.ui.top_menu.register("opentalk", "OpenTalk", "ex_app/img/app.svg", True)
        nc.set_init_status(100)
        LOGGER.info("OpenTalk initialization complete")
    else:
        LOGGER.warning("OpenTalk controller did not start - registering UI anyway")
        nc.ui.resources.set_script("top_menu", "opentalk", "js/opentalk-iframe-loader")
        nc.ui.top_menu.register("opentalk", "OpenTalk", "ex_app/img/app.svg", True)
        nc.set_init_status(100)


# -- Token Endpoint (proxies to Keycloak ExApp) ------------------------------
@APP.get("/api/auth/token")
async def get_auth_token(request: Request):
    """Get a Keycloak token for the current NC user via the Keycloak ExApp.

    Called by the OpenTalk frontend (inside iframe) to get a pre-authenticated
    token without browser OIDC redirects.
    """
    import base64

    nc_user_id = request.headers.get("NC-USER-ID", "")
    if not nc_user_id:
        nc_user_id = request.headers.get("EX-APP-USER", "")
    if not nc_user_id:
        # Decode from AppAPI authorization header
        auth_header = request.headers.get("authorization-app-api", "")
        if auth_header:
            try:
                decoded = base64.b64decode(auth_header).decode("utf-8")
                nc_user_id = decoded.split(":")[0]
            except Exception:
                pass
    LOGGER.info("Auth token request for NC user: %s", nc_user_id)

    if not nc_user_id:
        return JSONResponse({"error": "No user context"}, status_code=401)

    try:
        # Call the Keycloak ExApp directly (container-to-container).
        # The /api/ routes are excluded from AppAPIAuthMiddleware and use
        # a shared secret for authentication.
        keycloak_api_secret = os.environ.get(
            "KEYCLOAK_API_SECRET", "keycloak-exapp-internal-secret"
        )
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{KEYCLOAK_EXAPP_URL}/api/token",
                headers={
                    "X-NC-USER-ID": nc_user_id,
                    "X-API-SECRET": keycloak_api_secret,
                },
                params={"client_id": "opentalk"},
                timeout=15,
            )
            if resp.status_code == 200:
                return JSONResponse(resp.json())
            else:
                LOGGER.error(
                    "Keycloak ExApp token error: %d %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return JSONResponse(
                    {"error": "Token acquisition failed"},
                    status_code=resp.status_code,
                )
    except Exception as e:
        LOGGER.error("Failed to get token from Keycloak ExApp: %s", str(e))
        return JSONResponse({"error": str(e)}, status_code=502)


# -- Frontend Config ---------------------------------------------------------
def get_frontend_config() -> str:
    """Generate runtime config.js for the OpenTalk web frontend.

    When server-side auth is available (Keycloak ExApp), the frontend
    is configured to skip OIDC login and use the injected token instead.
    """
    keycloak_browser_url = os.environ.get(
        "KEYCLOAK_BROWSER_URL", "http://localhost:8180"
    )
    oidc_authority = f"{keycloak_browser_url}/realms/{KEYCLOAK_REALM}"

    return f"""window.config = {{
    controller: window.location.host + "{PROXY_PREFIX}",
    baseUrl: window.location.origin + "{PROXY_PREFIX}/",
    insecure: true,
    oidcConfig: {{
        authority: "{oidc_authority}",
        clientId: "opentalk",
        scope: "openid profile email",
        redirectPath: "auth/callback",
        popupRedirectPath: "auth/popup_callback",
        signInUrl: "{oidc_authority}/protocol/openid-connect/auth",
    }},
}};"""


# -- Catch-All Proxy ---------------------------------------------------------
@APP.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
async def proxy(request: Request, path: str):
    """Serve frontend static files or proxy API requests to controller."""
    from starlette.responses import FileResponse

    # Serve ex_app static files (icons, JS)
    if path.startswith("ex_app/"):
        file_path = Path(__file__).parent.parent.parent / path
        if file_path.is_file():
            return FileResponse(str(file_path))

    # Serve runtime config.js (no-cache to prevent AppAPI proxy caching)
    if path == "config.js":
        return Response(
            content=get_frontend_config(),
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache, no-store"},
        )

    # Proxy API requests to the OpenTalk controller
    if path.startswith("v1/") or path.startswith("v1"):
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

    # Serve frontend static files
    if path == "" or path == "/":
        return _serve_index_html()

    file_path = FRONTEND_DIR / path
    if file_path.is_file():
        return FileResponse(str(file_path))

    # SPA fallback: serve index.html for unmatched routes
    index_path = FRONTEND_DIR / "index.html"
    if index_path.is_file():
        return _serve_index_html()

    return JSONResponse({"error": "Not found"}, status_code=404)


def _serve_index_html() -> Response:
    """Serve index.html with token bootstrap script injected.

    Injects a script that fetches a pre-authenticated Keycloak token from
    the /api/auth/token endpoint and stores it in sessionStorage in the
    format oidc-client-ts expects. This allows the OpenTalk frontend to
    skip the OIDC login redirect (which CSP blocks in iframes).
    """
    index_path = FRONTEND_DIR / "index.html"
    html = index_path.read_text()

    keycloak_browser_url = os.environ.get(
        "KEYCLOAK_BROWSER_URL", "http://localhost:8180"
    )
    oidc_authority = f"{keycloak_browser_url}/realms/{KEYCLOAK_REALM}"

    # Inject bootstrap script before config.js. Nextcloud's AppAPI proxy
    # auto-adds CSP nonce to all <script> tags, so inline scripts work.
    # Uses synchronous XHR to ensure tokens are in localStorage before the
    # React app initializes (async fetch would race with app startup).
    bootstrap_script = f"""<script>
(function() {{
    try {{
        var xhr = new XMLHttpRequest();
        xhr.open('GET', '{PROXY_PREFIX}/api/auth/token', false);
        xhr.send();
        if (xhr.status === 200) {{
            var data = JSON.parse(xhr.responseText);
            localStorage.setItem('access_token', data.access_token);
            if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);
            if (data.id_token) localStorage.setItem('id_token', data.id_token);
            try {{
                var payload = JSON.parse(atob(data.access_token.split('.')[1]));
                localStorage.setItem('server_time_offset', String((payload.iat * 1000) - Date.now()));
            }} catch(e) {{}}
            if (data.id_token) {{
                var xhr2 = new XMLHttpRequest();
                xhr2.open('POST', '{PROXY_PREFIX}/v1/auth/login', false);
                xhr2.setRequestHeader('Content-Type', 'application/json');
                xhr2.send(JSON.stringify({{id_token: data.id_token}}));
            }}
            console.log('[OpenTalk ExApp] Token pre-loaded');
        }}
    }} catch(e) {{
        console.warn('[OpenTalk ExApp] Bootstrap error:', e);
    }}
}})();
</script>"""
    html = html.replace(
        f'<script src="{PROXY_PREFIX}/config.js">',
        f'{bootstrap_script}\n    <script src="{PROXY_PREFIX}/config.js">',
    )
    return Response(content=html, media_type="text/html")


# -- Entry Point -------------------------------------------------------------
if __name__ == "__main__":
    os.chdir(Path(__file__).parent)
    run_app(APP, log_level="info")
