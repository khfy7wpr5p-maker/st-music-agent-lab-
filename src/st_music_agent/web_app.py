from __future__ import annotations

import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .operator_console import OperatorConsoleError, OperatorConsoleService
from .task_execution import GuardedTaskService, TaskExecutionConfig, TaskExecutionError

_MAX_POST_BYTES = 32_768
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True, slots=True)
class AppResponse:
    status: int
    content_type: str
    body: bytes


class OperatorConsoleApplication:
    """Dependency-free HTTP application over the guarded ST Music Agent core."""

    def __init__(
        self,
        service: OperatorConsoleService | None = None,
        task_service: GuardedTaskService | None = None,
        *,
        session_token: str | None = None,
    ) -> None:
        self.service = service or OperatorConsoleService()
        self.task_service = task_service
        self.session_token = session_token or secrets.token_urlsafe(32)

    @property
    def writes_enabled(self) -> bool:
        return bool(self.task_service is not None and self.task_service.config.enabled)

    def dispatch(
        self,
        method: str,
        target: str,
        *,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> AppResponse:
        parsed = urlsplit(target)
        query = parse_qs(parsed.query, keep_blank_values=True)
        ref = query.get("ref", ["main"])[0]
        try:
            if method == "GET":
                return self._dispatch_get(parsed.path, ref)
            if method == "POST" and parsed.path in {
                "/api/tasks/preview",
                "/api/tasks/run",
                "/api/tasks/open-pr",
            }:
                return self._dispatch_task_post(parsed.path, body, headers)
            return self._json(405, {"error": "method_not_allowed"})
        except (OperatorConsoleError, TaskExecutionError, ValueError, TypeError) as exc:
            return self._json(400, {"error": "invalid_request", "detail": str(exc)})
        except Exception as exc:  # noqa: BLE001 - HTTP boundary converts adapter failures to JSON.
            detail = " ".join(str(exc).split())[:300] or exc.__class__.__name__
            return self._json(502, {"error": "operation_unavailable", "detail": detail})

    def _dispatch_get(self, path: str, ref: str) -> AppResponse:
        if path == "/":
            return AppResponse(200, "text/html; charset=utf-8", _INDEX_HTML.encode("utf-8"))
        if path == "/api/health":
            payload = self.service.health()
            payload["task_execution_enabled"] = self.writes_enabled
            payload["mutation_enabled"] = self.writes_enabled
            return self._json(200, payload)
        if path == "/api/session":
            return self._json(
                200,
                {
                    "writes_enabled": self.writes_enabled,
                    "session_token": self.session_token,
                    "merge_enabled": False,
                    "production_actions_authorized": False,
                },
            )
        if path == "/api/capabilities":
            payload = self.service.action_capabilities()
            write = payload.get("write")
            if isinstance(write, dict):
                write["feature_branch_task_execution"] = self.writes_enabled
            return self._json(200, payload)
        if path == "/api/projects":
            return self._json(200, self.service.list_projects(ref))
        if path == "/api/plan":
            return self._json(200, self.service.verified_plan(ref))
        project_prefix = "/api/projects/"
        if path.startswith(project_prefix):
            project = path[len(project_prefix) :]
            if not project or "/" in project:
                return self._json(404, {"error": "not_found"})
            return self._json(200, self.service.project_snapshot(project, ref))
        task_prefix = "/api/tasks/status/"
        if path.startswith(task_prefix):
            if self.task_service is None:
                return self._json(503, {"error": "task_service_unavailable"})
            task_id = path[len(task_prefix) :]
            return self._json(200, self.task_service.status(task_id))
        return self._json(404, {"error": "not_found"})

    def _dispatch_task_post(
        self,
        path: str,
        body: bytes | None,
        headers: Mapping[str, str] | None,
    ) -> AppResponse:
        if self.task_service is None:
            return self._json(503, {"error": "task_service_unavailable"})
        if self._header(headers, "x-st-session") != self.session_token:
            return self._json(403, {"error": "invalid_session"})
        payload = self._decode_json(body)
        if path == "/api/tasks/preview":
            project = payload.get("project")
            instruction = payload.get("instruction")
            if not isinstance(project, str) or not isinstance(instruction, str):
                raise TypeError("project and instruction must be text")
            preview = self.task_service.preview(project, instruction)
            return self._json(200, preview.as_dict())
        if not self.writes_enabled:
            return self._json(403, {"error": "task_execution_disabled"})
        task_id = payload.get("task_id")
        if not isinstance(task_id, str):
            raise TypeError("task_id must be text")
        if path == "/api/tasks/run":
            return self._json(200, self.task_service.run(task_id).as_dict())
        if path == "/api/tasks/open-pr":
            return self._json(200, {"pull_request": dict(self.task_service.open_pull_request(task_id))})
        return self._json(404, {"error": "not_found"})

    @staticmethod
    def _decode_json(body: bytes | None) -> dict[str, Any]:
        if body is None or not body:
            raise ValueError("JSON request body is required")
        if len(body) > _MAX_POST_BYTES:
            raise ValueError("request body exceeds configured limit")
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid UTF-8 JSON") from exc
        if not isinstance(decoded, dict):
            raise TypeError("request JSON must be an object")
        return decoded

    @staticmethod
    def _header(headers: Mapping[str, str] | None, name: str) -> str | None:
        if headers is None:
            return None
        lowered = name.lower()
        for key, value in headers.items():
            if key.lower() == lowered:
                return value
        return None

    @staticmethod
    def _json(status: int, payload: dict[str, Any]) -> AppResponse:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return AppResponse(status, "application/json; charset=utf-8", encoded)


def make_handler(application: OperatorConsoleApplication) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._send(application.dispatch("GET", self.path))

        def do_POST(self) -> None:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._send(OperatorConsoleApplication._json(415, {"error": "json_required"}))
                return
            raw_length = self.headers.get("Content-Length")
            try:
                length = int(raw_length or "0")
            except ValueError:
                self._send(OperatorConsoleApplication._json(400, {"error": "invalid_length"}))
                return
            if length < 1:
                self._send(OperatorConsoleApplication._json(400, {"error": "body_required"}))
                return
            if length > _MAX_POST_BYTES:
                self._send(OperatorConsoleApplication._json(413, {"error": "body_too_large"}))
                return
            body = self.rfile.read(length)
            headers = {key: value for key, value in self.headers.items()}
            self._send(application.dispatch("POST", self.path, body=body, headers=headers))

        def _send(self, response: AppResponse) -> None:
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'",
            )
            self.end_headers()
            self.wfile.write(response.body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def serve_operator_console(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    token_env: str | None = "GITHUB_TOKEN",
    api_base: str = "https://api.github.com",
    task_config: TaskExecutionConfig | None = None,
) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    if task_config is not None and task_config.enabled and host not in _LOOPBACK_HOSTS:
        raise ValueError("APP2 write mode may bind only to a loopback host")
    service = OperatorConsoleService(token_env=token_env, api_base=api_base)
    resolved_task_config = task_config or TaskExecutionConfig(
        enabled=False,
        github_token_env=token_env or "GITHUB_TOKEN",
        github_api_base=api_base,
    )
    task_service = GuardedTaskService(resolved_task_config)
    application = OperatorConsoleApplication(service, task_service)
    server = ThreadingHTTPServer((host, port), make_handler(application))
    print(f"ST Music Agent operator console: http://{host}:{port}")
    if application.writes_enabled:
        print("Mode: guarded feature-branch task execution enabled; PRs require a human click.")
    else:
        print("Mode: read-only evidence + task preview; start with --enable-writes to execute tasks.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


_INDEX_HTML = r"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ST Music Agent</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#e8ecf3;background:#090d14}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 15% 0,#17253a 0,#090d14 38%,#070a10 100%);min-height:100vh}.shell{max-width:1180px;margin:auto;padding:24px}.top{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin:10px 0 22px}.eyebrow{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:#8da2c0}.title{font-size:clamp(30px,6vw,54px);font-weight:750;letter-spacing:-.04em;margin:5px 0 4px}.subtitle{color:#9aa9bd;max-width:760px;line-height:1.55}.badge{white-space:nowrap;border:1px solid #244b3c;background:#102a21;color:#8de2ba;padding:8px 11px;border-radius:999px;font-size:12px}.badge.warn{border-color:#614920;background:#2f2412;color:#f2c97f}.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}.button{appearance:none;border:1px solid #2b3b52;background:#111a28;color:#e8ecf3;padding:10px 14px;border-radius:10px;font-weight:650;cursor:pointer}.button:hover{background:#17243a}.button.primary{background:#d9e5ff;color:#0c1420;border-color:#d9e5ff}.button.danger{border-color:#654343;background:#2b181b;color:#ffc4c7}.button:disabled{opacity:.5;cursor:wait}.meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:20px 0}.metric,.card,.panel{border:1px solid #202b3b;background:rgba(14,20,31,.86);box-shadow:0 18px 60px rgba(0,0,0,.22);border-radius:16px}.metric{padding:15px}.metric small{display:block;color:#8190a6;margin-bottom:6px}.metric strong{font-size:16px}.section-title{font-size:18px;margin:27px 0 12px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.card{padding:18px;min-height:230px}.card-head{display:flex;justify-content:space-between;gap:10px}.card h3{margin:0;font-size:18px}.repo{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:#718198;margin-top:5px;overflow-wrap:anywhere}.state{display:inline-block;margin-top:15px;padding:5px 8px;border-radius:7px;background:#172335;color:#adc2e0;font-size:11px}.state.error{background:#351b1d;color:#f4a8ad}.summary{line-height:1.52;color:#c0cad8;font-size:14px}.next{margin-top:14px;border-top:1px solid #202b3b;padding-top:12px;font-size:13px;color:#99abc4}.next b{color:#d7e3f5}.warnings{font-size:12px;color:#dcb27c;padding-left:18px}.panel{padding:18px;margin-top:14px}.panel.empty{color:#7e8da3}.plan-row{display:grid;grid-template-columns:34px 1fr;gap:12px;padding:13px 0;border-top:1px solid #202b3b}.plan-row:first-child{border-top:0}.rank{width:30px;height:30px;display:grid;place-items:center;border-radius:50%;background:#172335;color:#b9cae2;font-weight:700}.plan-action{font-weight:650}.plan-project,.muted{color:#8798b0;font-size:12px;margin-top:3px}.task-form{display:grid;grid-template-columns:220px 1fr;gap:12px}.task-form select,.task-form textarea{width:100%;border:1px solid #2b3b52;background:#0c131e;color:#e8ecf3;border-radius:10px;padding:11px;font:inherit}.task-form textarea{min-height:120px;resize:vertical}.task-result{margin-top:14px;border-top:1px solid #202b3b;padding-top:14px;line-height:1.5}.kv{display:grid;grid-template-columns:145px 1fr;gap:8px;font-size:13px;margin:5px 0}.kv span:first-child{color:#7789a2}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}.footer{color:#65758d;font-size:12px;margin:30px 0 10px}.loading{animation:pulse 1.1s infinite alternate}@keyframes pulse{from{opacity:.45}to{opacity:1}}@media(max-width:760px){.shell{padding:16px}.top{display:block}.badge{display:inline-block;margin-top:12px}.grid,.meta,.task-form{grid-template-columns:1fr}.title{font-size:38px}.kv{grid-template-columns:1fr}}
</style>
</head>
<body>
<main class="shell">
  <header class="top">
    <div><div class="eyebrow">ST Music Agent Lab</div><h1 class="title">Operator Console</h1><div class="subtitle">ST projelerini okur, planı doğrular ve APP2 write modu açık olduğunda yalnız policy-approved feature branch üzerinde kontrollü görev çalıştırır.</div></div>
    <div class="badge" id="modeBadge">SAFE MODE</div>
  </header>
  <div class="toolbar"><button class="button primary" id="refresh">Projeleri yenile</button><button class="button" id="planButton">Doğrulanmış plan oluştur</button></div>
  <section class="meta"><div class="metric"><small>Uygulama</small><strong id="health">Bağlanıyor…</strong></div><div class="metric"><small>Feature-branch execution</small><strong id="mutation">Kapalı</strong></div><div class="metric"><small>Merge / Production</small><strong>Kapalı / İnsan gerekli</strong></div></section>
  <h2 class="section-title">Projeler</h2><section class="grid" id="projects"><div class="card loading">Kanıtlar okunuyor…</div></section>
  <h2 class="section-title">Doğrulanmış portföy planı</h2><section class="panel empty" id="plan">Henüz plan oluşturulmadı.</section>
  <h2 class="section-title">Kontrollü görev</h2>
  <section class="panel">
    <div class="task-form"><select id="taskProject"><option value="score_restore">Score Restore</option><option value="musicxml_guitar_tab">MusicXML → Guitar TAB</option><option value="score_editor">Score Editor</option><option value="real_time_score_following">Real-Time Score Following</option></select><textarea id="taskInstruction" placeholder="Örn: README içinde Stage 12 durum açıklamasını güncelle. Başka dosyaya dokunma."></textarea></div>
    <div class="toolbar"><button class="button" id="previewTask">Görevi önizle</button><button class="button primary" id="runTask" disabled>Feature branch üzerinde çalıştır</button><button class="button danger" id="openPr" disabled>PR aç — insan işlemi</button></div>
    <div class="muted" id="writeHint">Görev çalıştırma durumu okunuyor…</div><div class="task-result" id="taskResult">Henüz görev yok.</div>
  </section>
  <div class="footer">APP2: model sadece host tarafından bağlanan feature branch’e yazabilir. PR ayrı insan tıklamasıdır. Merge/deploy/training/canonicalization/rollback endpoint’i yoktur.</div>
</main>
<script>
const $=s=>document.querySelector(s);const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]));let sessionToken="",writesEnabled=false,currentTask=null;
async function json(url,options={}){const r=await fetch(url,{cache:"no-store",...options});const p=await r.json();if(!r.ok)throw new Error(p.detail||p.error||`HTTP ${r.status}`);return p}
async function post(url,payload){return json(url,{method:"POST",headers:{"Content-Type":"application/json","X-ST-Session":sessionToken},body:JSON.stringify(payload)})}
function projectCard(p){if(p.availability!=="ok")return `<article class="card"><div class="card-head"><div><h3>${esc(p.name)}</h3><div class="repo">${esc(p.repository)}</div></div></div><span class="state error">EVIDENCE ERROR</span><p class="summary">${esc(p.error)}</p></article>`;const s=p.snapshot||{};const warnings=(s.warnings||[]).map(w=>`<li>${esc(w)}</li>`).join("");return `<article class="card"><div class="card-head"><div><h3>${esc(p.name)}</h3><div class="repo">${esc(p.repository)}</div></div></div><span class="state">${esc(s.state)}</span><p class="summary">${esc(s.summary)}</p>${warnings?`<ul class="warnings">${warnings}</ul>`:""}<div class="next"><b>Sonraki güvenli sınır:</b><br>${esc(s.next_safe_boundary||"Belirtilmedi")}</div></article>`}
async function load(){const b=$("#refresh");b.disabled=true;try{const [h,p,c,s]=await Promise.all([json("/api/health"),json("/api/projects"),json("/api/capabilities"),json("/api/session")]);sessionToken=s.session_token;writesEnabled=s.writes_enabled;$("#health").textContent=h.status==="ok"?"Çalışıyor":"Sorun";$("#mutation").textContent=writesEnabled?"Açık":"Kapalı";$("#modeBadge").textContent=writesEnabled?"GUARDED WRITE MODE":"READ / PREVIEW MODE";$("#modeBadge").className=writesEnabled?"badge warn":"badge";$("#writeHint").textContent=writesEnabled?"Yazma modu yalnız feature branch için açık. PR ve merge otomatik değildir.":"Önizleme yapılabilir. Çalıştırmak için uygulamayı --enable-writes ile yerelde başlat.";$("#projects").innerHTML=p.projects.map(projectCard).join("")}catch(e){$("#health").textContent="Bağlantı hatası";$("#projects").innerHTML=`<div class="card"><span class="state error">ERROR</span><p>${esc(e.message)}</p></div>`}finally{b.disabled=false}}
async function buildPlan(){const b=$("#planButton"),box=$("#plan");b.disabled=true;box.className="panel loading";box.textContent="Kanıtlar yeniden okunuyor ve plan doğrulanıyor…";try{const p=await json("/api/plan");const v=p.verification||{};const rows=(p.plan?.candidates||[]).map(c=>`<div class="plan-row"><div class="rank">${esc(c.rank)}</div><div><div class="plan-action">${esc(c.action)}</div><div class="plan-project">${esc(c.project)} · ${esc(c.category)}</div></div></div>`).join("");box.className="panel";box.innerHTML=`<div class="badge">VERIFIER: ${esc((v.status||"").toUpperCase())}</div>${rows}`}catch(e){box.className="panel";box.innerHTML=`<span class="state error">PLAN ERROR</span><p>${esc(e.message)}</p>`}finally{b.disabled=false}}
function previewHtml(p){return `<div class="kv"><span>Repository</span><b class="mono">${esc(p.repository)}</b></div><div class="kv"><span>Base</span><span class="mono">${esc(p.base_branch)} @ ${esc(p.base_sha)}</span></div><div class="kv"><span>Feature branch</span><span class="mono">${esc(p.feature_branch)}</span></div><div class="kv"><span>Branch policy</span><span>${esc(p.policy?.create_branch)}</span></div><div class="kv"><span>Write policy</span><span>${esc(p.policy?.write_file)}</span></div><div class="kv"><span>PR policy</span><span>${esc(p.policy?.open_pull_request)}</span></div>`}
async function previewTask(){const box=$("#taskResult"),b=$("#previewTask");b.disabled=true;try{const p=await post("/api/tasks/preview",{project:$("#taskProject").value,instruction:$("#taskInstruction").value});currentTask=p;box.innerHTML=previewHtml(p);$("#runTask").disabled=!writesEnabled;$("#openPr").disabled=true}catch(e){currentTask=null;box.innerHTML=`<span class="state error">PREVIEW ERROR</span><p>${esc(e.message)}</p>`;$("#runTask").disabled=true;$("#openPr").disabled=true}finally{b.disabled=false}}
async function runTask(){if(!currentTask)return;const b=$("#runTask"),box=$("#taskResult");b.disabled=true;box.innerHTML=previewHtml(currentTask)+`<p class="loading">Agent feature branch üzerinde çalışıyor…</p>`;try{const r=await post("/api/tasks/run",{task_id:currentTask.task_id});box.innerHTML=previewHtml(currentTask)+`<div class="kv"><span>Head</span><span class="mono">${esc(r.head_sha)}</span></div><div class="kv"><span>Model</span><span>${esc(r.model_name)}</span></div><div class="kv"><span>Tool calls</span><span>${esc(r.tool_calls)}</span></div><p>${esc(r.final_message?.content||"Görev tamamlandı.")}</p>`;$("#openPr").disabled=false}catch(e){box.innerHTML=previewHtml(currentTask)+`<span class="state error">RUN ERROR</span><p>${esc(e.message)}</p>`;b.disabled=false}}
async function openPr(){if(!currentTask)return;const b=$("#openPr"),box=$("#taskResult");b.disabled=true;try{const r=await post("/api/tasks/open-pr",{task_id:currentTask.task_id});const pr=r.pull_request||{};box.innerHTML+=`<div class="kv"><span>Pull Request</span><span>#${esc(pr.number)} · ${esc(pr.state)}</span></div><p class="muted">PR açıldı. Merge ayrı insan/host işlemidir.</p>`}catch(e){box.innerHTML+=`<span class="state error">PR ERROR</span><p>${esc(e.message)}</p>`;b.disabled=false}}
$("#refresh").addEventListener("click",load);$("#planButton").addEventListener("click",buildPlan);$("#previewTask").addEventListener("click",previewTask);$("#runTask").addEventListener("click",runTask);$("#openPr").addEventListener("click",openPr);load();
</script>
</body>
</html>"""
