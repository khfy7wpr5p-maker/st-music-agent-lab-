from __future__ import annotations

import json
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .operator_console import OperatorConsoleError, OperatorConsoleService


@dataclass(frozen=True, slots=True)
class AppResponse:
    status: int
    content_type: str
    body: bytes


class OperatorConsoleApplication:
    """Small dependency-free HTTP application for the first runnable ST operator console."""

    def __init__(self, service: OperatorConsoleService | None = None) -> None:
        self.service = service or OperatorConsoleService()

    def dispatch(self, method: str, target: str) -> AppResponse:
        if method != "GET":
            return self._json(405, {"error": "method_not_allowed"})
        parsed = urlsplit(target)
        query = parse_qs(parsed.query, keep_blank_values=True)
        ref = query.get("ref", ["main"])[0]
        try:
            if parsed.path == "/":
                return AppResponse(200, "text/html; charset=utf-8", _INDEX_HTML.encode("utf-8"))
            if parsed.path == "/api/health":
                return self._json(200, self.service.health())
            if parsed.path == "/api/capabilities":
                return self._json(200, self.service.action_capabilities())
            if parsed.path == "/api/projects":
                return self._json(200, self.service.list_projects(ref))
            if parsed.path == "/api/plan":
                return self._json(200, self.service.verified_plan(ref))
            prefix = "/api/projects/"
            if parsed.path.startswith(prefix):
                project = parsed.path[len(prefix) :]
                if not project or "/" in project:
                    return self._json(404, {"error": "not_found"})
                return self._json(200, self.service.project_snapshot(project, ref))
        except OperatorConsoleError as exc:
            return self._json(400, {"error": "invalid_request", "detail": str(exc)})
        except Exception as exc:  # noqa: BLE001 - HTTP boundary converts adapter failures to JSON.
            detail = " ".join(str(exc).split())[:300] or exc.__class__.__name__
            return self._json(502, {"error": "evidence_unavailable", "detail": detail})
        return self._json(404, {"error": "not_found"})

    @staticmethod
    def _json(status: int, payload: dict[str, Any]) -> AppResponse:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return AppResponse(status, "application/json; charset=utf-8", body)


def make_handler(application: OperatorConsoleApplication) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._send(application.dispatch("GET", self.path))

        def do_POST(self) -> None:
            self._send(application.dispatch("POST", self.path))

        def _send(self, response: AppResponse) -> None:
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
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
) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    service = OperatorConsoleService(token_env=token_env, api_base=api_base)
    application = OperatorConsoleApplication(service)
    server = ThreadingHTTPServer((host, port), make_handler(application))
    print(f"ST Music Agent operator console: http://{host}:{port}")
    print("Mode: read-only evidence + verified planning; production mutations remain disabled.")
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
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#e8ecf3;background:#090d14}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 15% 0,#17253a 0,#090d14 38%,#070a10 100%);min-height:100vh}.shell{max-width:1180px;margin:auto;padding:24px}.top{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin:10px 0 22px}.eyebrow{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:#8da2c0}.title{font-size:clamp(30px,6vw,54px);font-weight:750;letter-spacing:-.04em;margin:5px 0 4px}.subtitle{color:#9aa9bd;max-width:720px;line-height:1.55}.badge{white-space:nowrap;border:1px solid #244b3c;background:#102a21;color:#8de2ba;padding:8px 11px;border-radius:999px;font-size:12px}.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}.button{appearance:none;border:1px solid #2b3b52;background:#111a28;color:#e8ecf3;padding:10px 14px;border-radius:10px;font-weight:650;cursor:pointer}.button:hover{background:#17243a}.button.primary{background:#d9e5ff;color:#0c1420;border-color:#d9e5ff}.button:disabled{opacity:.5;cursor:wait}.meta{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:20px 0}.metric,.card,.plan{border:1px solid #202b3b;background:rgba(14,20,31,.86);box-shadow:0 18px 60px rgba(0,0,0,.22);border-radius:16px}.metric{padding:15px}.metric small{display:block;color:#8190a6;margin-bottom:6px}.metric strong{font-size:16px}.section-title{font-size:18px;margin:27px 0 12px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.card{padding:18px;min-height:230px}.card-head{display:flex;justify-content:space-between;gap:10px}.card h3{margin:0;font-size:18px}.repo{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:#718198;margin-top:5px;overflow-wrap:anywhere}.state{display:inline-block;margin-top:15px;padding:5px 8px;border-radius:7px;background:#172335;color:#adc2e0;font-size:11px}.state.error{background:#351b1d;color:#f4a8ad}.summary{line-height:1.52;color:#c0cad8;font-size:14px}.next{margin-top:14px;border-top:1px solid #202b3b;padding-top:12px;font-size:13px;color:#99abc4}.next b{color:#d7e3f5}.warnings{font-size:12px;color:#dcb27c;padding-left:18px}.plan{padding:18px;margin-top:14px}.plan.empty{color:#7e8da3}.plan-row{display:grid;grid-template-columns:34px 1fr;gap:12px;padding:13px 0;border-top:1px solid #202b3b}.plan-row:first-child{border-top:0}.rank{width:30px;height:30px;display:grid;place-items:center;border-radius:50%;background:#172335;color:#b9cae2;font-weight:700}.plan-action{font-weight:650}.plan-project{color:#8798b0;font-size:12px;margin-top:3px}.footer{color:#65758d;font-size:12px;margin:30px 0 10px}.loading{animation:pulse 1.1s infinite alternate}@keyframes pulse{from{opacity:.45}to{opacity:1}}@media(max-width:760px){.shell{padding:16px}.top{display:block}.badge{display:inline-block;margin-top:12px}.grid,.meta{grid-template-columns:1fr}.title{font-size:38px}}
</style>
</head>
<body>
<main class="shell">
  <header class="top">
    <div><div class="eyebrow">ST Music Agent Lab</div><h1 class="title">Operator Console</h1><div class="subtitle">Dört ST müzik projesinin güncel repository kanıtlarını tek ekranda okur, güvenli sonraki sınırı gösterir ve deterministik planı bağımsız verifier ile doğrular.</div></div>
    <div class="badge">READ-ONLY / SAFE</div>
  </header>
  <div class="toolbar"><button class="button primary" id="refresh">Projeleri yenile</button><button class="button" id="planButton">Doğrulanmış plan oluştur</button></div>
  <section class="meta"><div class="metric"><small>Uygulama</small><strong id="health">Bağlanıyor…</strong></div><div class="metric"><small>Mutation</small><strong id="mutation">Kapalı</strong></div><div class="metric"><small>Production onayı</small><strong>İnsan / Host gerekli</strong></div></section>
  <h2 class="section-title">Projeler</h2><section class="grid" id="projects"><div class="card loading">Kanıtlar okunuyor…</div></section>
  <h2 class="section-title">Doğrulanmış portföy planı</h2><section class="plan empty" id="plan">Henüz plan oluşturulmadı.</section>
  <div class="footer">APP1 — gerçek çalışan operator console. Bu sürüm bilerek mutation yapmaz; A1–A26 güvenlik katmanları korunur.</div>
</main>
<script>
const $=s=>document.querySelector(s);const esc=s=>String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[m]));
async function json(url){const r=await fetch(url,{cache:"no-store"});const p=await r.json();if(!r.ok)throw new Error(p.detail||p.error||`HTTP ${r.status}`);return p}
function projectCard(p){if(p.availability!=="ok")return `<article class="card"><div class="card-head"><div><h3>${esc(p.name)}</h3><div class="repo">${esc(p.repository)}</div></div></div><span class="state error">EVIDENCE ERROR</span><p class="summary">${esc(p.error)}</p></article>`;const s=p.snapshot||{};const warnings=(s.warnings||[]).map(w=>`<li>${esc(w)}</li>`).join("");return `<article class="card"><div class="card-head"><div><h3>${esc(p.name)}</h3><div class="repo">${esc(p.repository)}</div></div></div><span class="state">${esc(s.state)}</span><p class="summary">${esc(s.summary)}</p>${warnings?`<ul class="warnings">${warnings}</ul>`:""}<div class="next"><b>Sonraki güvenli sınır:</b><br>${esc(s.next_safe_boundary||"Belirtilmedi")}</div></article>`}
async function load(){const b=$("#refresh");b.disabled=true;try{const [h,p,c]=await Promise.all([json("/api/health"),json("/api/projects"),json("/api/capabilities")]);$("#health").textContent=h.status==="ok"?"Çalışıyor":"Sorun";$("#mutation").textContent=c.write.feature_branch_task_execution?"Açık":"Kapalı";$("#projects").innerHTML=p.projects.map(projectCard).join("")}catch(e){$("#health").textContent="Bağlantı hatası";$("#projects").innerHTML=`<div class="card"><span class="state error">ERROR</span><p>${esc(e.message)}</p></div>`}finally{b.disabled=false}}
async function buildPlan(){const b=$("#planButton"),box=$("#plan");b.disabled=true;box.className="plan loading";box.textContent="Kanıtlar yeniden okunuyor ve plan doğrulanıyor…";try{const p=await json("/api/plan");const v=p.verification||{};const rows=(p.plan?.candidates||[]).map(c=>`<div class="plan-row"><div class="rank">${esc(c.rank)}</div><div><div class="plan-action">${esc(c.action)}</div><div class="plan-project">${esc(c.project)} · ${esc(c.category)}</div></div></div>`).join("");box.className="plan";box.innerHTML=`<div class="badge">VERIFIER: ${esc((v.status||"").toUpperCase())}</div>${rows}`}catch(e){box.className="plan";box.innerHTML=`<span class="state error">PLAN ERROR</span><p>${esc(e.message)}</p>`}finally{b.disabled=false}}
$("#refresh").addEventListener("click",load);$("#planButton").addEventListener("click",buildPlan);load();
</script>
</body>
</html>"""
