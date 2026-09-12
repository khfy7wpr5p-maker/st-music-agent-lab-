from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .app7_task_execution import App7TaskService
from .app7_web_app import (
    _APP7_HTML,
    _LOOPBACK_HOSTS,
    _MIN_REMOTE_TOKEN_CHARS,
    App7OperatorConsoleApplication,
)
from .app8_graph_state import App8GraphStore, GraphStateError
from .operator_console import OperatorConsoleService
from .task_execution import TaskExecutionConfig, TaskExecutionError
from .web_app import AppResponse, make_handler


class App8OperatorConsoleApplication(App7OperatorConsoleApplication):
    """APP8E operator console: APP7 capabilities plus authenticated read-only graph views."""

    def __init__(
        self,
        service: OperatorConsoleService,
        task_service: App7TaskService,
        graph_store: App8GraphStore,
        *,
        session_token: str | None = None,
        remote_read_only: bool = False,
        remote_auth_digest: str | None = None,
    ) -> None:
        super().__init__(
            service,
            task_service,
            session_token=session_token,
            remote_read_only=remote_read_only,
            remote_auth_digest=remote_auth_digest,
        )
        self.graph_store = graph_store

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
                return AppResponse(200, "text/html; charset=utf-8", _APP8_HTML.encode("utf-8"))

            if parsed.path.startswith("/api/app8/graphs"):
                if self.remote_read_only and not self._remote_authorized(headers):
                    return self._json(401, {"error": "remote_auth_required"})
                if method != "GET":
                    return self._json(405, {"error": "app8_graphs_read_only"})
                if parsed.path == "/api/app8/graphs":
                    query = parse_qs(parsed.query)
                    raw_limit = query.get("limit", ["20"])[0]
                    try:
                        limit = int(raw_limit)
                    except ValueError as exc:
                        raise ValueError("limit must be an integer") from exc
                    return self._json(
                        200,
                        {
                            "schema_version": "1.0.0",
                            "graphs": self.graph_store.recent_graphs(limit),
                            "graph_mutations_enabled": False,
                            "merge_enabled": False,
                            "production_actions_authorized": False,
                        },
                    )

                verify_suffix = "/verify"
                graph_prefix = "/api/app8/graphs/"
                if parsed.path.startswith(graph_prefix):
                    remainder = unquote(parsed.path[len(graph_prefix) :])
                    verify = remainder.endswith(verify_suffix)
                    graph_id = remainder[: -len(verify_suffix)] if verify else remainder
                    if not graph_id or "/" in graph_id:
                        return self._json(404, {"error": "not_found"})
                    payload = (
                        self.graph_store.verify_graph(graph_id)
                        if verify
                        else self.graph_store.graph_view(graph_id)
                    )
                    return self._json(200, payload)
                return self._json(404, {"error": "not_found"})

            return super().dispatch(method, target, body=body, headers=headers)
        except (GraphStateError, TaskExecutionError, ValueError, TypeError) as exc:
            return self._json(400, {"error": "invalid_request", "detail": str(exc)})
        except Exception as exc:  # noqa: BLE001 - HTTP boundary normalizes adapter failures.
            detail = " ".join(str(exc).split())[:300] or exc.__class__.__name__
            return self._json(502, {"error": "operation_unavailable", "detail": detail})


def serve_operator_console(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    token_env: str | None = "GITHUB_TOKEN",
    api_base: str = "https://api.github.com",
    task_config: TaskExecutionConfig | None = None,
    state_path: str | Path | None = None,
    graph_state_path: str | Path | None = None,
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
            raise ValueError("APP8E remote mode is read-only and cannot enable task writes")
        if not remote_auth_token_env:
            raise ValueError("APP8E remote mode requires --remote-auth-token-env")
        raw_token = os.environ.get(remote_auth_token_env)
        if not isinstance(raw_token, str) or len(raw_token) < _MIN_REMOTE_TOKEN_CHARS:
            raise ValueError("remote auth token must contain at least 24 characters")
        if non_loopback and not remote_secure_transport_attested:
            raise ValueError(
                "non-loopback APP8E remote mode requires explicit secure-transport attestation"
            )
        remote_digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    else:
        if non_loopback:
            raise ValueError(
                "APP8E non-loopback binding is allowed only in authenticated remote read-only mode"
            )
        remote_digest = None

    service = OperatorConsoleService(token_env=token_env, api_base=api_base)
    task_service = App7TaskService(config, state_path=state_path)
    graph_store = App8GraphStore(graph_state_path)
    application = App8OperatorConsoleApplication(
        service,
        task_service,
        graph_store,
        remote_read_only=remote_read_only,
        remote_auth_digest=remote_digest,
    )
    server = ThreadingHTTPServer((host, port), make_handler(application))
    print(f"ST Music Agent APP8E operator console: http://{host}:{port}")
    print(f"APP8 graph journal: {graph_store.path}")
    if remote_read_only:
        print("Mode: authenticated remote READ-ONLY; task and graph mutations unavailable.")
        if non_loopback:
            print("Transport: operator explicitly attested a private/encrypted transport boundary.")
    elif application.writes_enabled:
        print("Mode: local guarded APP2-APP7 task execution + APP8 graph observability.")
        print("APP8 graph surface remains read-only; merge remains unavailable.")
    else:
        print("Mode: local read/review/audit + persistent APP8 graph observability.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _build_app8_html() -> str:
    html = _APP7_HTML
    html = html.replace("ST Music Agent APP7", "ST Music Agent APP8E")
    html = html.replace("APP7 Audit Replay Console", "APP8E Supervision Graph Console")
    html = html.replace(
        "Deterministik audit verify/replay ve authenticated remote read-only operator; merge yetkisi yok.",
        "Kalıcı APP8 supervision/coordination graph görünümü, deterministic resume/audit; merge yetkisi yok.",
    )
    panel = r'''
<h2 class="section">APP8 supervision graphs</h2>
<section class="panel">
  <div class="toolbar"><button id="loadApp8Graphs" class="button">Graph geçmişini yükle</button></div>
  <div class="muted">APP8E bu ekranda yalnız kalıcı graph journal ve deterministic replay gösterir. Graph mutation, PR, merge ve production yetkisi yoktur.</div>
  <div id="app8GraphList" style="margin-top:12px" class="muted">Henüz graph yüklenmedi.</div>
  <div id="app8GraphDetail" style="margin-top:12px" class="muted">Bir graph seçildiğinde ayrıntı burada görünür.</div>
</section>
'''
    html = html.replace('<h2 class="section">Kalıcı geçmiş</h2>', panel + '<h2 class="section">Kalıcı geçmiş</h2>')
    script = r'''
function graphButton(g){return `<button class="button" data-app8-graph="${esc(g.graph_id)}">${esc(g.graph_id)}</button><span class="badge">${esc(g.disposition)}</span><span class="muted mono">${esc(g.plan_fingerprint.slice(0,12))}</span>`}
async function loadApp8Graphs(){try{const p=await req("/api/app8/graphs?limit=30");const root=$("#app8GraphList");root.innerHTML=p.graphs.length?p.graphs.map(g=>`<div class="toolbar">${graphButton(g)}</div>`).join(""):"Kayıtlı APP8 graph yok.";root.querySelectorAll("[data-app8-graph]").forEach(b=>b.onclick=()=>loadApp8Graph(b.dataset.app8Graph))}catch(e){$("#app8GraphList").textContent=e.message}}
async function loadApp8Graph(id){try{const p=await req(`/api/app8/graphs/${encodeURIComponent(id)}`);const v=await req(`/api/app8/graphs/${encodeURIComponent(id)}/verify`);$("#app8GraphDetail").innerHTML=`<div class="kv"><span>Graph</span><b>${esc(p.graph_id)}</b></div><div class="kv"><span>Tür</span><b>${esc(p.kind)}</b></div><div class="kv"><span>Durum</span><b>${esc(p.replay.disposition)}</b></div><div class="kv"><span>Event</span><b>${esc(p.event_count)}</b></div><div class="kv"><span>Plan</span><span class="mono">${esc(p.plan_fingerprint)}</span></div><div class="kv"><span>Replay</span><span class="mono">${esc(p.replay.replay_fingerprint)}</span></div><div class="kv"><span>Verify</span><b>${esc(v.status)}</b></div><div class="kv"><span>Audit</span><span class="mono">${esc(v.verification_sha256)}</span></div>`}catch(e){$("#app8GraphDetail").textContent=e.message}}
$("#loadApp8Graphs").onclick=loadApp8Graphs;
'''
    html = html.replace("</script>", script + "\n</script>")
    return html


_APP8_HTML = _build_app8_html()
