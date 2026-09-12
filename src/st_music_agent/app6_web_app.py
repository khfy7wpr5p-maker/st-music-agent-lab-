from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .app5_task_execution import App5TaskService
from .app5_web_app import _APP5_HTML, App5OperatorConsoleApplication
from .app6_task_execution import App6TaskService
from .operator_console import OperatorConsoleService
from .task_execution import TaskExecutionConfig, TaskExecutionError
from .web_app import AppResponse, make_handler

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class App6OperatorConsoleApplication(App5OperatorConsoleApplication):
    """APP6 HTTP surface for validator health, trusted resolution evidence and audit export."""

    task_service: App6TaskService

    def dispatch(
        self,
        method: str,
        target: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> AppResponse:
        parsed = urlsplit(target)
        try:
            if method == "GET" and parsed.path == "/":
                return AppResponse(200, "text/html; charset=utf-8", _APP6_HTML.encode("utf-8"))
            prefix = "/api/tasks/audit/"
            if method == "GET" and parsed.path.startswith(prefix):
                task_id = unquote(parsed.path[len(prefix) :])
                if not task_id or "/" in task_id:
                    return self._json(404, {"error": "not_found"})
                return self._json(200, self.task_service.audit_bundle(task_id))
            return super().dispatch(method, target, body=body, headers=headers)
        except (TaskExecutionError, ValueError, TypeError) as exc:
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
) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    if task_config is not None and task_config.enabled and host not in _LOOPBACK_HOSTS:
        raise ValueError("APP6 write mode may bind only to a loopback host")
    service = OperatorConsoleService(token_env=token_env, api_base=api_base)
    resolved_task_config = task_config or TaskExecutionConfig(
        enabled=False,
        github_token_env=token_env or "GITHUB_TOKEN",
        github_api_base=api_base,
    )
    task_service = App6TaskService(resolved_task_config, state_path=state_path)
    application = App6OperatorConsoleApplication(service, task_service)
    server = ThreadingHTTPServer((host, port), make_handler(application))
    print(f"ST Music Agent APP6 operator console: http://{host}:{port}")
    if application.writes_enabled:
        print("Mode: guarded execution + freshness + audit; merge remains unavailable.")
    else:
        print("Mode: read/preview/review/audit; task execution is disabled.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _build_app6_html() -> str:
    html = _APP5_HTML
    html = html.replace("ST Music Agent APP5", "ST Music Agent APP6")
    html = html.replace("APP5 Validation & Review Console", "APP6 Health & Audit Console")
    html = html.replace(
        "Exact diff, proje-özel validator ve PR review/thread kanıtı; merge yetkisi yok.",
        "Validator freshness, güvenilir thread resolution ve audit export; merge yetkisi yok.",
    )
    html = html.replace(
        '<button id="refreshCollab" class="button" disabled>PR review / thread yenile</button>',
        '<button id="refreshCollab" class="button" disabled>PR review / thread yenile</button>'
        '<button id="auditExport" class="button" disabled>Audit JSON</button>',
    )
    html = html.replace(
        "APP5 validator/review kanıtı merge yetkisi değildir.",
        "APP6 freshness/review/audit kanıtı merge yetkisi değildir.",
    )
    marker = '$("#refreshCollab").disabled=!pr;renderCollaboration(s.pr_collaboration)}'
    replacement = (
        '$("#refreshCollab").disabled=!pr;$("#auditExport").disabled=!taskId(s);'
        'renderHealth(s.validator_health);renderCollaboration(s.pr_collaboration)}'
    )
    html = html.replace(marker, replacement)
    helper = r'''
function renderHealth(h){if(!h)return;const task=$("#task");const old=document.querySelector("#validatorHealth");if(old)old.remove();const div=document.createElement("div");div.id="validatorHealth";div.className="kv";div.innerHTML=`<span>Validator health</span><b>${esc(h.effective_state||h.state)}</b>`;task.appendChild(div)}
async function auditExport(){if(!current)return;try{const a=await req(`/api/tasks/audit/${encodeURIComponent(current.task_id)}`);const blob=new Blob([JSON.stringify(a,null,2)],{type:"application/json"});const url=URL.createObjectURL(blob);const link=document.createElement("a");link.href=url;link.download=`st-music-agent-audit-${current.task_id.replace(/[^a-zA-Z0-9_-]/g,"_")}.json`;link.click();URL.revokeObjectURL(url)}catch(e){$("#task").insertAdjacentHTML("beforeend",`<div class="state bad">${esc(e.message)}</div>`)}}
'''
    html = html.replace("</script>", helper + "\n</script>")
    html = html.replace(
        '$("#refreshCollab").onclick=refreshCollaboration;$("#createRevision")',
        '$("#refreshCollab").onclick=refreshCollaboration;$("#auditExport").onclick=auditExport;$("#createRevision")',
    )
    return html


_APP6_HTML = _build_app6_html()
