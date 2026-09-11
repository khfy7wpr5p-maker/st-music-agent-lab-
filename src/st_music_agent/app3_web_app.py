from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .app3_task_execution import App3TaskService
from .operator_console import OperatorConsoleService
from .task_execution import TaskExecutionConfig, TaskExecutionError
from .web_app import AppResponse, OperatorConsoleApplication, make_handler

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class App3OperatorConsoleApplication(OperatorConsoleApplication):
    """APP3 HTTP surface: explicit evidence refresh, resumable status, no merge endpoint."""

    task_service: App3TaskService

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
                return AppResponse(200, "text/html; charset=utf-8", _APP3_HTML.encode("utf-8"))
            if method == "GET" and parsed.path == "/api/tasks":
                return self._json(200, {"tasks": self.task_service.recent_tasks()})
            if method == "POST" and parsed.path == "/api/tasks/refresh-evidence":
                if self._header(headers, "x-st-session") != self.session_token:
                    return self._json(403, {"error": "invalid_session"})
                payload = self._decode_json(body)
                task_id = payload.get("task_id")
                if not isinstance(task_id, str):
                    raise TypeError("task_id must be text")
                return self._json(200, self.task_service.refresh_evidence(task_id))
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
        raise ValueError("APP3 write mode may bind only to a loopback host")
    service = OperatorConsoleService(token_env=token_env, api_base=api_base)
    resolved_task_config = task_config or TaskExecutionConfig(
        enabled=False,
        github_token_env=token_env or "GITHUB_TOKEN",
        github_api_base=api_base,
    )
    task_service = App3TaskService(resolved_task_config, state_path=state_path)
    application = App3OperatorConsoleApplication(service, task_service)
    server = ThreadingHTTPServer((host, port), make_handler(application))
    print(f"ST Music Agent APP3 operator console: http://{host}:{port}")
    if application.writes_enabled:
        print("Mode: guarded task execution + exact evidence; PR requires VERIFIED_SUCCESS and click.")
    else:
        print("Mode: read/preview + persistent evidence; task execution is disabled.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


_APP3_HTML = r"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ST Music Agent APP3</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#e7edf7;background:#090d14}*{box-sizing:border-box}body{margin:0;background:#090d14;min-height:100vh}.shell{max-width:1120px;margin:auto;padding:22px}.top{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.eyebrow{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:#8999b1}.title{font-size:clamp(30px,6vw,50px);margin:4px 0;letter-spacing:-.04em}.sub,.muted{color:#8fa0b7;line-height:1.5}.badge,.state{display:inline-block;border:1px solid #2d425f;border-radius:999px;padding:6px 9px;font-size:11px;background:#111b29;color:#b9cbea}.badge.ok,.state.ok{border-color:#28523f;background:#10291f;color:#8ce0b5}.badge.warn,.state.warn{border-color:#644d23;background:#302511;color:#efca7f}.badge.bad,.state.bad{border-color:#65383d;background:#30171b;color:#f1a4aa}.toolbar{display:flex;gap:9px;flex-wrap:wrap;margin:16px 0}.button{border:1px solid #2b3b52;background:#121b29;color:#e7edf7;border-radius:10px;padding:10px 13px;font-weight:650;cursor:pointer}.button.primary{background:#dce7ff;color:#0c1420;border-color:#dce7ff}.button.danger{border-color:#6b4348;background:#2d191d;color:#ffc0c4}.button:disabled{opacity:.45;cursor:not-allowed}.panel,.card{border:1px solid #202b3b;background:#0f151f;border-radius:15px;padding:16px;margin-top:14px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.task-form{display:grid;grid-template-columns:220px 1fr;gap:10px}.task-form select,.task-form textarea{width:100%;border:1px solid #2b3b52;background:#0b111b;color:#e7edf7;border-radius:10px;padding:10px;font:inherit}.task-form textarea{min-height:108px;resize:vertical}.kv{display:grid;grid-template-columns:155px 1fr;gap:8px;margin:6px 0;font-size:13px}.kv>span:first-child{color:#788ba5}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}.timeline{display:grid;gap:8px;margin-top:12px}.step{border-left:3px solid #2a3a50;padding:8px 10px;background:#0b111a;border-radius:0 8px 8px 0}.step b{display:block;font-size:12px}.files,.validators,.runs{margin:8px 0 0;padding-left:18px;color:#b9c5d5;font-size:12px}.recent button{width:100%;text-align:left;margin-top:7px}.section-title{font-size:17px;margin:25px 0 9px}.footer{color:#667890;font-size:12px;margin:28px 0}.loading{opacity:.7}@media(max-width:760px){.shell{padding:14px}.top{display:block}.grid,.task-form,.kv{grid-template-columns:1fr}.title{font-size:36px}.badge{margin-top:10px}.button{flex:1}}
</style>
</head>
<body>
<main class="shell">
<header class="top"><div><div class="eyebrow">ST Music Agent Lab</div><h1 class="title">APP3 Operator Console</h1><div class="sub">Feature branch görevi, exact commit/diff kanıtı, CI/validator doğrulaması ve insan tıklamalı PR akışı.</div></div><span id="mode" class="badge">BAĞLANIYOR</span></header>
<div class="toolbar"><button id="reload" class="button primary">Durumu yenile</button><button id="loadTasks" class="button">Kayıtlı görevler</button></div>
<section class="grid"><div class="card"><div class="muted">Write mode</div><b id="writeMode">—</b></div><div class="card"><div class="muted">Merge / Production</div><b>Kapalı / Yetkisiz</b></div></section>
<h2 class="section-title">Yeni / devam eden görev</h2>
<section class="panel">
<div class="task-form"><select id="project"><option value="score_restore">Score Restore</option><option value="musicxml_guitar_tab">MusicXML → Guitar TAB</option><option value="score_editor">Score Editor</option><option value="real_time_score_following">Real-Time Score Following</option></select><textarea id="instruction" placeholder="Görevi açık ve sınırlandırılmış biçimde yazın."></textarea></div>
<div class="toolbar"><button id="preview" class="button">Önizle</button><button id="run" class="button primary" disabled>Feature branch üzerinde çalıştır</button><button id="refreshEvidence" class="button" disabled>CI / validator yenile</button><button id="openPr" class="button danger" disabled>PR aç — insan işlemi</button></div>
<div id="task" class="muted">Henüz görev seçilmedi.</div>
</section>
<h2 class="section-title">Kalıcı görev geçmişi</h2><section id="recent" class="panel recent muted">Kayıtlı görevleri görmek için düğmeye basın.</section>
<div class="footer">APP3 otomatik merge, deployment, training, canonicalization veya rollback yetkisi vermez. CI başarısı tek başına müzikal doğruluk değildir.</div>
</main>
<script>
const $=s=>document.querySelector(s);const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]));let token="",writes=false,current=null;
async function req(url,opt={}){const r=await fetch(url,{cache:"no-store",...opt});const p=await r.json();if(!r.ok)throw new Error(p.detail||p.error||`HTTP ${r.status}`);return p}async function post(url,p){return req(url,{method:"POST",headers:{"Content-Type":"application/json","X-ST-Session":token},body:JSON.stringify(p)})}
function badge(outcome){if(outcome==="VERIFIED_SUCCESS")return"state ok";if(outcome==="FAILED")return"state bad";if(outcome==="REVIEW_REQUIRED")return"state warn";return"state"}
function render(s){current=s.preview||current;const c=s.commit||{},ci=s.ci||{},vals=s.validators||[],pr=s.pull_request||null;const files=(c.changed_files||[]).map(f=>`<li><span class="mono">${esc(f.path)}</span> +${esc(f.additions)} −${esc(f.deletions)}</li>`).join("");const runs=(ci.runs||[]).map(r=>`<li>${esc(r.name)} · ${esc(r.status)} · ${esc(r.conclusion||"—")}</li>`).join("");const vr=vals.map(v=>`<li><b>${esc(v.name)}</b>: ${esc(v.status)} — ${esc(v.message)}</li>`).join("");$("#task").innerHTML=`<span class="${badge(s.outcome)}">${esc(s.outcome||"PREVIEW")}</span><div class="kv"><span>Stage</span><b>${esc(s.stage||"PREVIEWED")}</b></div><div class="kv"><span>Task</span><span class="mono">${esc(s.task_id||s.preview?.task_id)}</span></div><div class="kv"><span>Repository</span><span class="mono">${esc(s.preview?.repository)}</span></div><div class="kv"><span>Feature branch</span><span class="mono">${esc(s.preview?.feature_branch)}</span></div>${c.head_sha?`<div class="kv"><span>Exact HEAD</span><span class="mono">${esc(c.head_sha)}</span></div>`:""}${files?`<div class="step"><b>Changed files</b><ul class="files">${files}</ul></div>`:""}${ci.state?`<div class="step"><b>CI: ${esc(ci.state)}</b><div class="muted">${esc(ci.message||"")}</div>${runs?`<ul class="runs">${runs}</ul>`:""}</div>`:""}${vr?`<div class="step"><b>Validators</b><ul class="validators">${vr}</ul></div>`:""}${pr?`<div class="step"><b>PR #${esc(pr.number)}</b><div class="mono">head ${esc(pr.head_sha||c.head_sha)} · base ${esc(pr.base_sha||"—")}</div></div>`:""}`;$("#refreshEvidence").disabled=!c.head_sha||s.stage==="FAILED"||s.stage==="PR_OPENED";$("#openPr").disabled=s.outcome!=="VERIFIED_SUCCESS"||!!pr;$("#run").disabled=!writes||!["PREVIEWED","BRANCH_CREATED","AGENT_RUNNING"].includes(s.stage||"PREVIEWED")}
async function boot(){try{const s=await req("/api/session");token=s.session_token;writes=s.writes_enabled;$("#writeMode").textContent=writes?"Açık — feature branch only":"Kapalı";$("#mode").textContent=writes?"GUARDED WRITE":"READ / PREVIEW";$("#mode").className=writes?"badge warn":"badge ok"}catch(e){$("#mode").textContent="HATA";$("#mode").className="badge bad"}}
async function preview(){try{const p=await post("/api/tasks/preview",{project:$("#project").value,instruction:$("#instruction").value});current=p;render({task_id:p.task_id,stage:"PREVIEWED",outcome:"WORKING",preview:p});$("#run").disabled=!writes}catch(e){$("#task").innerHTML=`<span class="state bad">PREVIEW ERROR</span> ${esc(e.message)}`}}
async function run(){if(!current)return;$("#run").disabled=true;$("#task").insertAdjacentHTML("afterbegin",`<div class="loading">Agent çalışıyor…</div>`);try{await post("/api/tasks/run",{task_id:current.task_id});render(await req(`/api/tasks/status/${encodeURIComponent(current.task_id)}`))}catch(e){$("#task").insertAdjacentHTML("beforeend",`<div class="state bad">RUN ERROR: ${esc(e.message)}</div>`)}}
async function refreshEvidence(){if(!current)return;try{render(await post("/api/tasks/refresh-evidence",{task_id:current.task_id}))}catch(e){$("#task").insertAdjacentHTML("beforeend",`<div class="state bad">EVIDENCE ERROR: ${esc(e.message)}</div>`)}}
async function openPr(){if(!current)return;try{await post("/api/tasks/open-pr",{task_id:current.task_id});render(await req(`/api/tasks/status/${encodeURIComponent(current.task_id)}`))}catch(e){$("#task").insertAdjacentHTML("beforeend",`<div class="state bad">PR ERROR: ${esc(e.message)}</div>`)}}
async function recent(){try{const p=await req("/api/tasks");$("#recent").innerHTML=p.tasks.length?p.tasks.map(t=>`<button class="button" data-task="${esc(t.task_id)}"><b>${esc(t.preview?.project||"task")}</b> · ${esc(t.outcome)}<br><span class="mono">${esc(t.task_id)}</span></button>`).join(""):"Henüz kalıcı görev yok.";document.querySelectorAll("[data-task]").forEach(b=>b.onclick=async()=>{const id=b.dataset.task;const s=await req(`/api/tasks/status/${encodeURIComponent(id)}`);current=s.preview;render(s)})}catch(e){$("#recent").textContent=e.message}}
$("#preview").onclick=preview;$("#run").onclick=run;$("#refreshEvidence").onclick=refreshEvidence;$("#openPr").onclick=openPr;$("#loadTasks").onclick=recent;$("#reload").onclick=async()=>{await boot();if(current?.task_id)render(await req(`/api/tasks/status/${encodeURIComponent(current.task_id)}`))};boot();
</script>
</body></html>"""
