from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Mapping
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .app6_web_app import _APP6_HTML, App6OperatorConsoleApplication
from .app7_task_execution import App7TaskService
from .operator_console import OperatorConsoleService
from .task_execution import TaskExecutionConfig, TaskExecutionError
from .web_app import AppResponse, make_handler

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_MIN_REMOTE_TOKEN_CHARS = 24
_MAX_AUTH_HEADER_CHARS = 1024


class App7OperatorConsoleApplication(App6OperatorConsoleApplication):
    """APP7 local console plus authenticated, read-only remote operator surface."""

    task_service: App7TaskService

    def __init__(
        self,
        service: OperatorConsoleService,
        task_service: App7TaskService,
        *,
        session_token: str | None = None,
        remote_read_only: bool = False,
        remote_auth_digest: str | None = None,
    ) -> None:
        super().__init__(service, task_service, session_token=session_token)
        self.remote_read_only = remote_read_only
        self.remote_auth_digest = remote_auth_digest

    def dispatch(
        self,
        method: str,
        target: str,
        *,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> AppResponse:
        parsed = urlsplit(target)
        try:
            if method == "GET" and parsed.path == "/":
                return AppResponse(200, "text/html; charset=utf-8", _APP7_HTML.encode("utf-8"))
            if method == "GET" and parsed.path == "/api/remote-mode":
                return self._json(
                    200,
                    {
                        "remote_read_only": self.remote_read_only,
                        "auth_required": self.remote_read_only,
                        "writes_enabled": False if self.remote_read_only else self.writes_enabled,
                        "merge_enabled": False,
                        "production_actions_authorized": False,
                    },
                )

            if self.remote_read_only:
                if not self._remote_authorized(headers):
                    return self._json(401, {"error": "remote_auth_required"})
                if method != "GET":
                    return self._json(405, {"error": "remote_read_only"})
                if parsed.path == "/api/session":
                    return self._json(
                        200,
                        {
                            "writes_enabled": False,
                            "session_token": "",
                            "remote_read_only": True,
                            "merge_enabled": False,
                            "production_actions_authorized": False,
                        },
                    )

            verify_prefix = "/api/tasks/audit-verify/"
            if method == "GET" and parsed.path.startswith(verify_prefix):
                task_id = unquote(parsed.path[len(verify_prefix) :])
                if not task_id or "/" in task_id:
                    return self._json(404, {"error": "not_found"})
                return self._json(200, self.task_service.verify_current_audit(task_id))

            replay_prefix = "/api/tasks/replay/"
            if method == "GET" and parsed.path.startswith(replay_prefix):
                task_id = unquote(parsed.path[len(replay_prefix) :])
                if not task_id or "/" in task_id:
                    return self._json(404, {"error": "not_found"})
                return self._json(200, self.task_service.replay_task(task_id))

            return super().dispatch(method, target, body=body, headers=headers)
        except (TaskExecutionError, ValueError, TypeError) as exc:
            return self._json(400, {"error": "invalid_request", "detail": str(exc)})
        except Exception as exc:  # noqa: BLE001 - HTTP boundary normalizes adapter failures.
            detail = " ".join(str(exc).split())[:300] or exc.__class__.__name__
            return self._json(502, {"error": "operation_unavailable", "detail": detail})

    def _remote_authorized(self, headers: Mapping[str, str] | None) -> bool:
        digest = self.remote_auth_digest
        if not self.remote_read_only or not isinstance(digest, str):
            return not self.remote_read_only
        authorization = self._header(headers, "authorization")
        if not isinstance(authorization, str) or len(authorization) > _MAX_AUTH_HEADER_CHARS:
            return False
        prefix = "Bearer "
        if not authorization.startswith(prefix):
            return False
        token = authorization[len(prefix) :]
        if len(token) < _MIN_REMOTE_TOKEN_CHARS:
            return False
        candidate = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return hmac.compare_digest(candidate, digest)


def serve_operator_console(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    token_env: str | None = "GITHUB_TOKEN",
    api_base: str = "https://api.github.com",
    task_config: TaskExecutionConfig | None = None,
    state_path: str | Path | None = None,
    remote_read_only: bool = False,
    remote_auth_token_env: str | None = None,
    remote_secure_transport_attested: bool = False,
) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    config = task_config or TaskExecutionConfig(
        enabled=False,
        github_token_env=token_env or "GITHUB_TOKEN",
        github_api_base=api_base,
    )
    non_loopback = host not in _LOOPBACK_HOSTS
    if remote_read_only:
        if config.enabled:
            raise ValueError("APP7 remote mode is read-only and cannot enable task writes")
        if not remote_auth_token_env:
            raise ValueError("APP7 remote mode requires --remote-auth-token-env")
        raw_token = os.environ.get(remote_auth_token_env)
        if not isinstance(raw_token, str) or len(raw_token) < _MIN_REMOTE_TOKEN_CHARS:
            raise ValueError("remote auth token must contain at least 24 characters")
        if non_loopback and not remote_secure_transport_attested:
            raise ValueError(
                "non-loopback APP7 remote mode requires explicit secure-transport attestation"
            )
        remote_digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    else:
        if non_loopback:
            raise ValueError(
                "APP7 non-loopback binding is allowed only in authenticated remote read-only mode"
            )
        remote_digest = None

    service = OperatorConsoleService(token_env=token_env, api_base=api_base)
    task_service = App7TaskService(config, state_path=state_path)
    application = App7OperatorConsoleApplication(
        service,
        task_service,
        remote_read_only=remote_read_only,
        remote_auth_digest=remote_digest,
    )
    server = ThreadingHTTPServer((host, port), make_handler(application))
    print(f"ST Music Agent APP7 operator console: http://{host}:{port}")
    if remote_read_only:
        print("Mode: authenticated remote READ-ONLY; mutations and session write token unavailable.")
        if non_loopback:
            print("Transport: operator explicitly attested a private/encrypted transport boundary.")
    elif application.writes_enabled:
        print("Mode: local guarded execution + audit replay; merge remains unavailable.")
    else:
        print("Mode: local read/preview/review/audit/replay; task execution is disabled.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _build_app7_html() -> str:
    html = _APP6_HTML
    html = html.replace("ST Music Agent APP6", "ST Music Agent APP7")
    html = html.replace("APP6 Health & Audit Console", "APP7 Audit Replay Console")
    html = html.replace(
        "Validator freshness, güvenilir thread resolution ve audit export; merge yetkisi yok.",
        "Deterministik audit verify/replay ve authenticated remote read-only operator; merge yetkisi yok.",
    )
    html = html.replace(
        '<header class="top">',
        '<section id="remoteAuth" class="panel" style="display:none"><b>Remote read-only authentication</b><div class="toolbar"><input id="remoteToken" type="password" autocomplete="current-password" placeholder="Bearer token" style="flex:1;min-width:220px;background:#0b111b;color:#e7edf7;border:1px solid #2b3b52;border-radius:10px;padding:10px"><button id="remoteLogin" class="button primary">Bağlan</button><button id="remoteLogout" class="button">Oturumu temizle</button></div><div class="muted">Token yalnız sessionStorage içinde tutulur. Remote modda tüm mutation endpointleri kapalıdır.</div></section><header class="top">',
    )
    html = html.replace(
        '<button id="auditExport" class="button" disabled>Audit JSON</button>',
        '<button id="auditExport" class="button" disabled>Audit JSON</button>'
        '<button id="auditVerify" class="button" disabled>Audit doğrula</button>'
        '<button id="auditReplay" class="button" disabled>Journal replay</button>',
    )
    html = html.replace(
        '<h2 class="section">Kalıcı geçmiş</h2>',
        '<h2 class="section">Audit verification / replay</h2><section id="auditVerification" class="panel muted">Bir görev seçildiğinde doğrulama sonucu burada görünür.</section><h2 class="section">Kalıcı geçmiş</h2>',
    )
    old_req = 'async function req(url,opt={}){const r=await fetch(url,{cache:"no-store",...opt});const p=await r.json();if(!r.ok)throw new Error(p.detail||p.error||`HTTP ${r.status}`);return p}'
    new_req = 'let remoteToken=sessionStorage.getItem("stRemoteToken")||"",remoteMode=false;async function req(url,opt={}){const headers={...(opt.headers||{})};if(remoteToken)headers["Authorization"]="Bearer "+remoteToken;const r=await fetch(url,{cache:"no-store",...opt,headers});const p=await r.json();if(!r.ok)throw new Error(p.detail||p.error||`HTTP ${r.status}`);return p}'
    html = html.replace(old_req, new_req)
    old_boot = 'async function boot(){const s=await req("/api/session");token=s.session_token;writes=s.writes_enabled;$("#writeMode").textContent=writes?"Açık — feature branch only":"Kapalı";$("#mode").textContent=writes?"GUARDED WRITE":"READ / REVIEW";$("#mode").className=writes?"badge warn":"badge ok"}'
    new_boot = r'''function remoteLock(){if(!remoteMode)return;["#preview","#run","#refreshEvidence","#loadReview","#ackReview","#openPr","#createRevision","#refreshCollab"].forEach(id=>{const el=$(id);if(el)el.disabled=true})}
async function boot(){const m=await fetch("/api/remote-mode",{cache:"no-store"}).then(r=>r.json());remoteMode=!!m.remote_read_only;$("#remoteAuth").style.display=remoteMode?"block":"none";if(remoteMode&&!remoteToken){writes=false;$("#writeMode").textContent="Remote read-only";$("#mode").textContent="AUTH REQUIRED";$("#mode").className="badge warn";remoteLock();return}const s=await req("/api/session");token=s.session_token||"";writes=!!s.writes_enabled&&!remoteMode;$("#writeMode").textContent=remoteMode?"Remote read-only":writes?"Açık — feature branch only":"Kapalı";$("#mode").textContent=remoteMode?"REMOTE READ-ONLY":writes?"GUARDED WRITE":"READ / REVIEW";$("#mode").className=remoteMode?"badge ok":writes?"badge warn":"badge ok";remoteLock()}
async function remoteLogin(){remoteToken=$("#remoteToken").value.trim();if(!remoteToken)return;sessionStorage.setItem("stRemoteToken",remoteToken);try{await boot();await recent()}catch(e){sessionStorage.removeItem("stRemoteToken");remoteToken="";$("#mode").textContent=e.message}}
function remoteLogout(){sessionStorage.removeItem("stRemoteToken");remoteToken="";location.reload()}'''
    html = html.replace(old_boot, new_boot)
    helper = r'''
const app7Render=render;render=function(s){app7Render(s);$("#auditVerify").disabled=!taskId(s);$("#auditReplay").disabled=!taskId(s);remoteLock()}
function renderAuditResult(title,p){$("#auditVerification").innerHTML=`<div class="kv"><span>${esc(title)}</span><b>${esc(p.status||p.verified)}</b></div><div class="kv"><span>Stage</span><b>${esc(p.replay?.derived_stage||p.derived_stage||"—")}</b></div><div class="kv"><span>Outcome</span><b>${esc(p.replay?.derived_outcome||p.derived_outcome||"—")}</b></div><div class="kv"><span>Digest</span><span class="mono">${esc(p.verification_sha256||p.replay_sha256||"")}</span></div>${(p.reasons||p.violations||[]).length?`<div class="state bad">${esc((p.reasons||p.violations).join("; "))}</div>`:""}`}
async function auditVerify(){if(!current)return;try{renderAuditResult("Audit verify",await req(`/api/tasks/audit-verify/${encodeURIComponent(current.task_id)}`))}catch(e){$("#auditVerification").textContent=e.message}}
async function auditReplay(){if(!current)return;try{renderAuditResult("Journal replay",await req(`/api/tasks/replay/${encodeURIComponent(current.task_id)}`))}catch(e){$("#auditVerification").textContent=e.message}}
'''
    html = html.replace("</script>", helper + "\n</script>")
    html = html.replace(
        '$("#refreshCollab").onclick=refreshCollaboration;$("#auditExport").onclick=auditExport;',
        '$("#refreshCollab").onclick=refreshCollaboration;$("#auditExport").onclick=auditExport;$("#auditVerify").onclick=auditVerify;$("#auditReplay").onclick=auditReplay;',
    )
    html = html.replace(
        '$("#loadTasks").onclick=recent;boot().catch',
        '$("#loadTasks").onclick=recent;$("#remoteLogin").onclick=remoteLogin;$("#remoteLogout").onclick=remoteLogout;boot().catch',
    )
    return html


_APP7_HTML = _build_app7_html()
