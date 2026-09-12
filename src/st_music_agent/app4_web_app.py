from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .app3_web_app import App3OperatorConsoleApplication
from .app4_task_execution import App4TaskService
from .operator_console import OperatorConsoleService
from .task_execution import TaskExecutionConfig, TaskExecutionError
from .web_app import AppResponse, make_handler

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class App4OperatorConsoleApplication(App3OperatorConsoleApplication):
    """APP4 HTTP surface for exact diff review, acknowledgement and immutable revisions."""

    task_service: App4TaskService

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
                return AppResponse(200, "text/html; charset=utf-8", _APP4_HTML.encode("utf-8"))
            if method == "POST" and parsed.path in {
                "/api/tasks/review",
                "/api/tasks/ack-review",
                "/api/tasks/revision",
                "/api/tasks/refresh-pr-review",
            }:
                if self._header(headers, "x-st-session") != self.session_token:
                    return self._json(403, {"error": "invalid_session"})
                payload = self._decode_json(body)
                if parsed.path == "/api/tasks/review":
                    task_id = payload.get("task_id")
                    if not isinstance(task_id, str):
                        raise TypeError("task_id must be text")
                    return self._json(200, self.task_service.review_bundle(task_id))
                if parsed.path == "/api/tasks/ack-review":
                    task_id = payload.get("task_id")
                    review_digest = payload.get("review_digest")
                    if not isinstance(task_id, str) or not isinstance(review_digest, str):
                        raise TypeError("task_id and review_digest must be text")
                    return self._json(
                        200,
                        self.task_service.acknowledge_review(task_id, review_digest),
                    )
                if parsed.path == "/api/tasks/revision":
                    parent_task_id = payload.get("parent_task_id")
                    instruction = payload.get("instruction")
                    mode = payload.get("mode")
                    if not all(
                        isinstance(value, str)
                        for value in (parent_task_id, instruction, mode)
                    ):
                        raise TypeError("parent_task_id, instruction and mode must be text")
                    return self._json(
                        200,
                        self.task_service.create_revision(
                            parent_task_id,
                            instruction,
                            mode=mode,
                        ),
                    )
                task_id = payload.get("task_id")
                if not isinstance(task_id, str):
                    raise TypeError("task_id must be text")
                return self._json(200, self.task_service.refresh_pr_review(task_id))
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
        raise ValueError("APP4 write mode may bind only to a loopback host")
    service = OperatorConsoleService(token_env=token_env, api_base=api_base)
    resolved_task_config = task_config or TaskExecutionConfig(
        enabled=False,
        github_token_env=token_env or "GITHUB_TOKEN",
        github_api_base=api_base,
    )
    task_service = App4TaskService(resolved_task_config, state_path=state_path)
    application = App4OperatorConsoleApplication(service, task_service)
    server = ThreadingHTTPServer((host, port), make_handler(application))
    print(f"ST Music Agent APP4 operator console: http://{host}:{port}")
    if application.writes_enabled:
        print("Mode: guarded execution + exact review acknowledgement; merge remains unavailable.")
    else:
        print("Mode: read/preview/review; task execution is disabled.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


_APP4_HTML = r"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ST Music Agent APP4</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#e7edf7;background:#090d14}*{box-sizing:border-box}body{margin:0;background:#090d14}.shell{max-width:1160px;margin:auto;padding:20px}.top{display:flex;justify-content:space-between;gap:14px}.eyebrow{font-size:12px;letter-spacing:.15em;text-transform:uppercase;color:#8798b0}.title{font-size:clamp(30px,6vw,48px);margin:4px 0}.muted{color:#8fa0b7;line-height:1.5}.badge,.state{display:inline-block;border:1px solid #2d425f;border-radius:999px;padding:6px 9px;font-size:11px;background:#111b29;color:#b9cbea}.ok{border-color:#28523f;background:#10291f;color:#8ce0b5}.warn{border-color:#644d23;background:#302511;color:#efca7f}.bad{border-color:#65383d;background:#30171b;color:#f1a4aa}.panel,.card{border:1px solid #202b3b;background:#0f151f;border-radius:15px;padding:15px;margin-top:13px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px}.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}.button{border:1px solid #2b3b52;background:#121b29;color:#e7edf7;border-radius:10px;padding:10px 12px;font-weight:650;cursor:pointer}.button.primary{background:#dce7ff;color:#0c1420}.button.danger{border-color:#6b4348;background:#2d191d;color:#ffc0c4}.button:disabled{opacity:.42;cursor:not-allowed}.form{display:grid;grid-template-columns:220px 1fr;gap:9px}.form select,.form textarea{width:100%;background:#0b111b;color:#e7edf7;border:1px solid #2b3b52;border-radius:10px;padding:10px;font:inherit}.form textarea{min-height:96px}.kv{display:grid;grid-template-columns:155px 1fr;gap:7px;margin:6px 0;font-size:13px}.kv>span:first-child{color:#788ba5}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}.review-file{border-top:1px solid #243143;padding-top:12px;margin-top:12px}.review-head{display:flex;gap:8px;justify-content:space-between;align-items:center}.patch{white-space:pre-wrap;word-break:break-word;background:#080c12;border:1px solid #202b3b;border-radius:10px;padding:11px;max-height:420px;overflow:auto;font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:#c9d4e3}.recent button{width:100%;text-align:left;margin-top:7px}.section{font-size:17px;margin:24px 0 8px}.footer{color:#667890;font-size:12px;margin:26px 0}@media(max-width:760px){.shell{padding:13px}.top{display:block}.grid,.form,.kv{grid-template-columns:1fr}.button{flex:1}.title{font-size:35px}}
</style></head>
<body><main class="shell">
<header class="top"><div><div class="eyebrow">ST Music Agent Lab</div><h1 class="title">APP4 Review Console</h1><div class="muted">Exact diff inceleme, insan onayı, immutable retry/amend lineage ve PR review kanıtı.</div></div><span id="mode" class="badge">BAĞLANIYOR</span></header>
<div class="grid"><div class="card"><div class="muted">Write mode</div><b id="writeMode">—</b></div><div class="card"><div class="muted">Merge / Production</div><b>Kapalı / Yetkisiz</b></div></div>
<h2 class="section">Görev</h2><section class="panel">
<div class="form"><select id="project"><option value="score_restore">Score Restore</option><option value="musicxml_guitar_tab">MusicXML → Guitar TAB</option><option value="score_editor">Score Editor</option><option value="real_time_score_following">Real-Time Score Following</option></select><textarea id="instruction" placeholder="Sınırlandırılmış mühendislik görevini yazın."></textarea></div>
<div class="toolbar"><button id="preview" class="button">Önizle</button><button id="run" class="button primary" disabled>Çalıştır</button><button id="refreshEvidence" class="button" disabled>CI / validator</button><button id="loadReview" class="button" disabled>Exact diff incele</button><button id="ackReview" class="button" disabled>Bu diff'i onayla</button><button id="openPr" class="button danger" disabled>PR aç — insan işlemi</button></div>
<div id="task" class="muted">Henüz görev seçilmedi.</div></section>
<h2 class="section">Exact diff review</h2><section id="review" class="panel muted">Commit oluştuğunda exact diff burada görüntülenir.</section>
<h2 class="section">Retry / Amend</h2><section class="panel"><div class="form"><select id="revisionMode"><option value="amend">Amend — mevcut commit için düzeltme</option><option value="retry">Retry — FAILED görev için yeni deneme</option></select><textarea id="revisionInstruction" placeholder="Yeni child task'ın neyi düzeltmesi gerektiğini yazın."></textarea></div><div class="toolbar"><button id="createRevision" class="button">Yeni child task oluştur</button></div><div id="revisionResult" class="muted">Parent görev değiştirilmez; yeni task kimliği oluşturulur.</div></section>
<h2 class="section">Kalıcı geçmiş</h2><section id="recent" class="panel recent muted"><button id="loadTasks" class="button">Kayıtlı görevleri getir</button></section>
<div class="footer">APP4 review acknowledgement merge yetkisi değildir. Merge/deploy/training/canonicalization/rollback uygulama dışında ve ayrı yetki sınırındadır.</div>
</main><script>
const $=s=>document.querySelector(s);const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]));let token="",writes=false,current=null,currentReview=null;
async function req(url,opt={}){const r=await fetch(url,{cache:"no-store",...opt});const p=await r.json();if(!r.ok)throw new Error(p.detail||p.error||`HTTP ${r.status}`);return p}async function post(url,p){return req(url,{method:"POST",headers:{"Content-Type":"application/json","X-ST-Session":token},body:JSON.stringify(p)})}
function badge(o){return o==="VERIFIED_SUCCESS"?"state ok":o==="FAILED"?"state bad":o==="REVIEW_REQUIRED"?"state warn":"state"}
function taskId(s){return s.task_id||s.preview?.task_id||current?.task_id}
function render(s){current=s.preview||current;const c=s.commit||{},ci=s.ci||{},ack=s.review_ack||null,lin=s.lineage||{},pr=s.pull_request||null,prr=s.pr_review||null;$("#task").innerHTML=`<span class="${badge(s.outcome)}">${esc(s.outcome||"WORKING")}</span><div class="kv"><span>Stage</span><b>${esc(s.stage||"PREVIEWED")}</b></div><div class="kv"><span>Task</span><span class="mono">${esc(taskId(s))}</span></div><div class="kv"><span>Branch</span><span class="mono">${esc(s.preview?.feature_branch||current?.feature_branch)}</span></div>${c.head_sha?`<div class="kv"><span>Exact HEAD</span><span class="mono">${esc(c.head_sha)}</span></div>`:""}${ci.state?`<div class="kv"><span>CI</span><b>${esc(ci.state)}</b></div>`:""}${ack?`<div class="kv"><span>Review ack</span><span class="mono">${esc(ack.review_digest)}</span></div>`:""}${lin.parent?`<div class="kv"><span>Parent</span><span class="mono">${esc(lin.parent.parent_task_id)}</span></div>`:""}${(lin.children||[]).length?`<div class="kv"><span>Children</span><span>${esc(lin.children.length)}</span></div>`:""}${pr?`<div class="kv"><span>PR</span><span>#${esc(pr.number)} · ${esc(pr.state||"open")}</span></div>`:""}${prr?`<div class="kv"><span>PR binding</span><b>${prr.exact_head_match?"EXACT":"MISMATCH"}</b></div>`:""}`;$("#run").disabled=!writes||!["PREVIEWED","BRANCH_CREATED","AGENT_RUNNING"].includes(s.stage||"PREVIEWED");$("#refreshEvidence").disabled=!c.head_sha||["FAILED","PR_OPENED"].includes(s.stage);$("#loadReview").disabled=!c.head_sha;$("#ackReview").disabled=!currentReview||!currentReview.complete||s.review_ready_for_pr;$("#openPr").disabled=s.outcome!=="VERIFIED_SUCCESS"||!s.review_ready_for_pr||!!pr}
function renderReview(r){currentReview=r;const files=(r.files||[]).map(f=>`<div class="review-file"><div class="review-head"><b class="mono">${esc(f.path)}</b><span class="state ${f.attention==="high"||f.attention==="incomplete"?"warn":""}">${esc(f.attention)}</span></div><div class="muted">${esc(f.status)} · +${esc(f.additions)} −${esc(f.deletions)} · ${esc(f.changes)} changes</div><pre class="patch">${esc(f.patch||"Patch görüntülenemiyor")}</pre></div>`).join("");$("#review").innerHTML=`<div class="kv"><span>Review digest</span><span class="mono">${esc(r.review_digest)}</span></div><div class="kv"><span>Complete</span><b>${r.complete?"EVET":"HAYIR — PR ack kapalı"}</b></div>${files}`;$("#ackReview").disabled=!r.complete}
async function boot(){const s=await req("/api/session");token=s.session_token;writes=s.writes_enabled;$("#writeMode").textContent=writes?"Açık — feature branch only":"Kapalı";$("#mode").textContent=writes?"GUARDED WRITE":"READ / REVIEW";$("#mode").className=writes?"badge warn":"badge ok"}
async function preview(){try{const p=await post("/api/tasks/preview",{project:$("#project").value,instruction:$("#instruction").value});current=p;currentReview=null;render({task_id:p.task_id,stage:"PREVIEWED",outcome:"WORKING",preview:p})}catch(e){$("#task").textContent=e.message}}
async function run(){if(!current)return;try{await post("/api/tasks/run",{task_id:current.task_id});render(await req(`/api/tasks/status/${encodeURIComponent(current.task_id)}`))}catch(e){$("#task").insertAdjacentHTML("beforeend",`<div class="state bad">${esc(e.message)}</div>`)}}
async function refreshEvidence(){if(!current)return;try{render(await post("/api/tasks/refresh-evidence",{task_id:current.task_id}))}catch(e){$("#task").insertAdjacentHTML("beforeend",`<div class="state bad">${esc(e.message)}</div>`)}}
async function loadReview(){if(!current)return;try{renderReview(await post("/api/tasks/review",{task_id:current.task_id}));render(await req(`/api/tasks/status/${encodeURIComponent(current.task_id)}`))}catch(e){$("#review").textContent=e.message}}
async function ackReview(){if(!current||!currentReview)return;try{render(await post("/api/tasks/ack-review",{task_id:current.task_id,review_digest:currentReview.review_digest}))}catch(e){$("#review").insertAdjacentHTML("afterbegin",`<div class="state bad">${esc(e.message)}</div>`)}}
async function openPr(){if(!current)return;try{await post("/api/tasks/open-pr",{task_id:current.task_id});render(await req(`/api/tasks/status/${encodeURIComponent(current.task_id)}`));await post("/api/tasks/refresh-pr-review",{task_id:current.task_id});render(await req(`/api/tasks/status/${encodeURIComponent(current.task_id)}`))}catch(e){$("#task").insertAdjacentHTML("beforeend",`<div class="state bad">${esc(e.message)}</div>`)}}
async function revision(){if(!current)return;try{const r=await post("/api/tasks/revision",{parent_task_id:current.task_id,mode:$("#revisionMode").value,instruction:$("#revisionInstruction").value});const c=r.child;$("#revisionResult").innerHTML=`Yeni ${esc(r.mode)} child: <span class="mono">${esc(c.task_id)}</span>`;current=c;currentReview=null;render({task_id:c.task_id,stage:"PREVIEWED",outcome:"WORKING",preview:c})}catch(e){$("#revisionResult").textContent=e.message}}
async function recent(){try{const p=await req("/api/tasks");$("#recent").innerHTML=p.tasks.length?p.tasks.map(t=>`<button class="button" data-task="${esc(t.task_id)}"><b>${esc(t.preview?.project||"task")}</b> · ${esc(t.outcome)}<br><span class="mono">${esc(t.task_id)}</span></button>`).join(""):"Henüz görev yok.";document.querySelectorAll("[data-task]").forEach(b=>b.onclick=async()=>{const s=await req(`/api/tasks/status/${encodeURIComponent(b.dataset.task)}`);current=s.preview;currentReview=null;render(s)})}catch(e){$("#recent").textContent=e.message}}
$("#preview").onclick=preview;$("#run").onclick=run;$("#refreshEvidence").onclick=refreshEvidence;$("#loadReview").onclick=loadReview;$("#ackReview").onclick=ackReview;$("#openPr").onclick=openPr;$("#createRevision").onclick=revision;$("#loadTasks").onclick=recent;boot().catch(e=>{$("#mode").textContent=e.message});
</script></body></html>"""
