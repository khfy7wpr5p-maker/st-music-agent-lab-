from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .app4_web_app import _APP4_HTML, App4OperatorConsoleApplication
from .app5_task_execution import App5TaskService
from .operator_console import OperatorConsoleService
from .task_execution import TaskExecutionConfig, TaskExecutionError
from .web_app import AppResponse, make_handler

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class App5OperatorConsoleApplication(App4OperatorConsoleApplication):
    """APP5 HTTP surface for project-aware validation and bounded PR collaboration evidence."""

    task_service: App5TaskService

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
                return AppResponse(200, "text/html; charset=utf-8", _APP5_HTML.encode("utf-8"))
            if method == "POST" and parsed.path == "/api/tasks/refresh-pr-collaboration":
                if self._header(headers, "x-st-session") != self.session_token:
                    return self._json(403, {"error": "invalid_session"})
                payload = self._decode_json(body)
                task_id = payload.get("task_id")
                if not isinstance(task_id, str):
                    raise TypeError("task_id must be text")
                return self._json(200, self.task_service.refresh_pr_collaboration(task_id))
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
        raise ValueError("APP5 write mode may bind only to a loopback host")
    service = OperatorConsoleService(token_env=token_env, api_base=api_base)
    resolved_task_config = task_config or TaskExecutionConfig(
        enabled=False,
        github_token_env=token_env or "GITHUB_TOKEN",
        github_api_base=api_base,
    )
    task_service = App5TaskService(resolved_task_config, state_path=state_path)
    application = App5OperatorConsoleApplication(service, task_service)
    server = ThreadingHTTPServer((host, port), make_handler(application))
    print(f"ST Music Agent APP5 operator console: http://{host}:{port}")
    if application.writes_enabled:
        print("Mode: guarded execution + project validators + review evidence; merge unavailable.")
    else:
        print("Mode: read/preview/review; task execution is disabled.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _build_app5_html() -> str:
    html = _APP4_HTML
    html = html.replace("ST Music Agent APP4", "ST Music Agent APP5")
    html = html.replace("APP4 Review Console", "APP5 Validation & Review Console")
    html = html.replace(
        "Exact diff inceleme, insan onayı, immutable retry/amend lineage ve PR review kanıtı.",
        "Exact diff, proje-özel validator ve PR review/thread kanıtı; merge yetkisi yok.",
    )
    html = html.replace(
        '<button id="openPr" class="button danger" disabled>PR aç — insan işlemi</button>',
        '<button id="openPr" class="button danger" disabled>PR aç — insan işlemi</button>'
        '<button id="refreshCollab" class="button" disabled>PR review / thread yenile</button>',
    )
    html = html.replace(
        '<h2 class="section">Kalıcı geçmiş</h2>',
        '<h2 class="section">PR collaboration</h2>'
        '<section id="collaboration" class="panel muted">PR açıldıktan sonra review ve thread kanıtı burada görünür.</section>'
        '<h2 class="section">Kalıcı geçmiş</h2>',
    )
    html = html.replace(
        "APP4 review acknowledgement merge yetkisi değildir.",
        "APP5 validator/review kanıtı merge yetkisi değildir.",
    )
    old_render_tail = '$("#openPr").disabled=s.outcome!=="VERIFIED_SUCCESS"||!s.review_ready_for_pr||!!pr}'
    new_render_tail = (
        '$("#openPr").disabled=s.outcome!=="VERIFIED_SUCCESS"||!s.review_ready_for_pr||!!pr;'
        '$("#refreshCollab").disabled=!pr;renderCollaboration(s.pr_collaboration)}'
    )
    html = html.replace(old_render_tail, new_render_tail)
    helper = r'''
function renderCollaboration(c){const el=$("#collaboration");if(!c){el.textContent="PR collaboration snapshot henüz yok.";return}const approvals=(c.exact_head_approvals||[]).join(", ")||"—";const changes=(c.exact_head_changes_requested||[]).join(", ")||"—";const threads=(c.threads||[]).map(t=>`<li><span class="mono">${esc(t.path||"conversation")}</span> · ${esc(t.comment_count)} yorum · resolution ${esc(t.resolution_state)}</li>`).join("");el.innerHTML=`<div class="kv"><span>Exact approvals</span><b>${esc(approvals)}</b></div><div class="kv"><span>Changes requested</span><b>${esc(changes)}</b></div><div class="kv"><span>Stale reviews</span><b>${esc(c.stale_review_count)}</b></div><div class="kv"><span>Threads</span><b>${esc(c.thread_count)}</b></div>${threads?`<ul class="validators">${threads}</ul>`:""}<div class="muted">Thread resolution state GitHub REST kanıtında yoksa unavailable kalır; bu merge onayı değildir.</div>`}
async function refreshCollaboration(){if(!current)return;try{render(await post("/api/tasks/refresh-pr-collaboration",{task_id:current.task_id}))}catch(e){$("#collaboration").textContent=e.message}}
'''
    html = html.replace("</script>", helper + "\n</script>")
    html = html.replace(
        '$("#openPr").onclick=openPr;$("#createRevision")',
        '$("#openPr").onclick=openPr;$("#refreshCollab").onclick=refreshCollaboration;$("#createRevision")',
    )
    return html


_APP5_HTML = _build_app5_html()
