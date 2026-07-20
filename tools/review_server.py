#!/usr/bin/env python3
"""Evidence Review Tool v3 — checklist-style fast triage.

Design principles (from Sentry, Playwright, Linear, App Store review research):
1. ONE ITEM AT A TIME — not a wall of cards. Show the current check, big and clear.
2. VISUAL-FIRST — screenshots/video dominate, text is secondary and collapsible.
3. ONE-TAP DECISIONS — ✓ / ✕ / skip. No forms, no dropdowns.
4. PROGRESS FEEL — "3 of 8" with a satisfying progress bar.
5. NO PROSE — max 2 sentences per check. Evidence speaks.
6. KEYBOARD SHORTCUTS — A=accept, R=reject, Space=next.
"""
from __future__ import annotations

import json
import sys
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
ATTACHMENTS_DIR = ROOT / "qa_runs" / "review_attachments"

app = FastAPI()
REPORTS: dict[str, dict[str, Any]] = {}
ATTACHMENTS: dict[str, Path] = {}
CLIENTS: list[WebSocket] = []


async def broadcast(msg: dict[str, Any]) -> None:
    alive = []
    for ws in CLIENTS:
        try:
            await ws.send_json(msg)
            alive.append(ws)
        except Exception:
            pass
    CLIENTS[:] = alive


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--pass:#22c55e;--fail:#ef4444;--warn:#f59e0b;--pending:#64748b;--bg:#0a0a0b;--card:#131316;--border:#1e1e24;--text:#e4e4e7;--muted:#71717a;--accent:#3b82f6}
body{font:16px/1.5 -apple-system,system-ui,sans-serif;background:var(--bg);color:var(--text);overflow:hidden}
.hidden{display:none!important}

/* Top bar */
.topbar{height:52px;border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 20px;gap:16px;background:var(--card)}
.topbar select{background:var(--bg);color:var(--accent);border:1px solid var(--border);border-radius:6px;padding:4px 8px;font-size:14px}
.topbar .progress-text{font-size:14px;color:var(--muted);font-variant-numeric:tabular-nums}
.topbar .progress-bar{flex:1;height:6px;background:var(--bg);border-radius:3px;overflow:hidden;max-width:300px}
.topbar .progress-fill{height:100%;background:var(--pass);transition:width .3s;border-radius:3px}
.topbar .gate{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
.topbar .gate.pass{color:var(--pass)}.topbar .gate.fail{color:var(--fail)}.topbar .gate.pending{color:var(--muted)}

/* Single check view */
.check-view{height:calc(100vh - 52px);display:flex;flex-direction:column;align-items:center;padding:24px;overflow-y:auto}

/* Empty state */
.empty-state{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--muted);gap:8px}
.empty-state h2{font-size:18px;font-weight:500}

/* Check card — full width, centered */
.check-card{width:100%;max-width:720px}
.check-header{display:flex;align-items:center;gap:12px;margin-bottom:16px}
.status-icon{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:700}
.status-icon.pass{background:rgba(34,197,94,.12);color:var(--pass)}
.status-icon.fail{background:rgba(239,68,68,.12);color:var(--fail)}
.status-icon.warn{background:rgba(245,158,11,.12);color:var(--warn)}
.status-icon.pending{background:rgba(100,116,139,.12);color:var(--pending)}
.check-title{font-size:18px;font-weight:600;flex:1}
.sev-badge{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;padding:3px 8px;border-radius:4px}
.sev-badge.critical{background:rgba(239,68,68,.15);color:#f87171}
.sev-badge.high{background:rgba(245,158,11,.15);color:#fbbf24}
.sev-badge.medium{background:rgba(59,130,246,.15);color:#60a5fa}
.sev-badge.low{background:rgba(100,116,139,.15);color:#94a3b8}

/* Observed — one line, bold */
.observed{font-size:15px;color:var(--text);margin-bottom:12px;line-height:1.5}

/* Collapsible details */
details{margin-bottom:12px}
summary{cursor:pointer;font-size:13px;color:var(--muted);user-select:none}
summary:hover{color:var(--text)}
details[open] summary{margin-bottom:6px}
.detail-content{font-size:13px;color:var(--muted);padding:8px 0}

/* Evidence — visual first */
.evidence-strip{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap}
.ev-item{cursor:pointer;border-radius:8px;overflow:hidden;border:1px solid var(--border);transition:border-color .1s}
.ev-item:hover{border-color:var(--accent)}
.ev-item.image{width:200px;height:130px}
.ev-item.image img{width:100%;height:100%;object-fit:cover}
.ev-item.video{width:200px;height:130px;position:relative;background:var(--card);display:flex;align-items:center;justify-content:center}
.ev-item.video::after{content:'▶';font-size:32px;color:var(--text)}
.ev-item.file{padding:8px 12px;display:flex;align-items:center;gap:6px;font-size:13px;color:var(--accent)}
.ev-label{font-size:11px;color:var(--muted);padding:2px 6px}

/* Decision buttons — big, clear, one tap */
.decisions{display:flex;gap:12px;margin-top:auto;padding-top:20px}
.btn-decide{padding:14px 32px;border-radius:12px;border:2px solid;font-size:15px;font-weight:600;cursor:pointer;transition:all .1s;background:transparent}
.btn-decide:active{transform:scale(.96)}
.btn-accept{border-color:var(--pass);color:var(--pass)}
.btn-accept:hover{background:rgba(34,197,94,.1)}
.btn-reject{border-color:var(--fail);color:var(--fail)}
.btn-reject:hover{background:rgba(239,68,68,.1)}
.btn-skip{border-color:var(--border);color:var(--muted)}
.btn-skip:hover{border-color:var(--muted)}

/* Keyboard hint */
.kbd-hint{margin-top:12px;font-size:12px;color:var(--muted);text-align:center}
.kbd{display:inline-block;padding:1px 6px;border:1px solid var(--border);border-radius:4px;font-family:monospace;font-size:11px;margin:0 2px}

/* Done state */
.done-state{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:12px}
.done-state h1{font-size:28px;font-weight:700}
.done-state .summary{font-size:15px;color:var(--muted);display:flex;gap:16px}
.done-state .summary span{display:flex;align-items:center;gap:4px}

/* Lightbox */
.lightbox{position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:100;display:none;align-items:center;justify-content:center;cursor:pointer}
.lightbox.show{display:flex}
.lightbox img{max-width:90vw;max-height:90vh;border-radius:8px}
.lightbox video{max-width:90vw;max-height:90vh;border-radius:8px}
.lightbox pre{max-width:80vw;max-height:80vh;overflow:auto;background:var(--card);padding:20px;border-radius:8px;border:1px solid var(--border);font-size:12px;color:var(--text)}

/* Completed check animation */
.check-card.deciding{animation:slideOut .25s forwards}
@keyframes slideOut{to{opacity:0;transform:translateX(40px)}}
</style>
</head>
<body>

<div class="topbar">
  <select id="reportSelect" onchange="loadReport(this.value)">
    <option value="">Select report...</option>
  </select>
  <span id="progressText" class="progress-text"></span>
  <div class="progress-bar"><div id="progressFill" class="progress-fill" style="width:0"></div></div>
  <span id="gateText" class="gate"></span>
</div>

<div id="mainView" class="check-view">
  <div class="empty-state">
    <h2>Select a report to begin</h2>
  </div>
</div>

<div id="lightbox" class="lightbox" onclick="this.classList.remove('show')"></div>

<script>
let report=null, currentIdx=0, decisions={};

function esc(s){return s?String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])):''}

function getEvidence(c){
  if(!report)return[];
  return (c.evidence_refs||[]).map(id=>report.evidence?.find(e=>e.evidence_id===id)).filter(Boolean);
}

function updateProgress(){
  if(!report)return;
  const checks=report.checks||[];
  const total=checks.length;
  const done=Object.keys(decisions).length;
  document.getElementById('progressText').textContent=total?`${done}/${total} reviewed`:'';
  document.getElementById('progressFill').style.width=(total?done/total*100:0)+'%';
  const g=report.summary?.gate||'pending';
  const gt=document.getElementById('gateText');
  gt.textContent=g.toUpperCase();
  gt.className='gate '+g;
}

function renderCheck(){
  const el=document.getElementById('mainView');
  if(!report){
    el.innerHTML='<div class="empty-state"><h2>Select a report to begin</h2></div>';
    return;
  }
  const checks=report.checks||[];
  if(currentIdx>=checks.length){
    const total=checks.length;
    const accepted=Object.values(decisions).filter(d=>d==='accepted').length;
    const rejected=Object.values(decisions).filter(d=>d==='rejected').length;
    const skipped=total-accepted-rejected;
    el.innerHTML=`<div class="done-state">
      <h1>${accepted+rejected===total?'All Reviewed':'Review Complete'}</h1>
      <div class="summary">
        <span><span style="color:var(--pass)">✓</span> ${accepted} accepted</span>
        <span><span style="color:var(--fail)">✕</span> ${rejected} rejected</span>
        <span style="color:var(--muted)">${skipped} skipped</span>
      </div>
      <p style="color:var(--muted);font-size:14px">Refresh the page to review again or push a new report.</p>
    </div>`;
    updateProgress();
    return;
  }
  const c=checks[currentIdx];
  const ev=getEvidence(c);
  const alreadyDecided=decisions[c.check_id];

  el.innerHTML=`<div class="check-card" id="checkCard">
    <div class="check-header">
      <div class="status-icon ${c.status}">${c.status==='pass'?'✓':c.status==='fail'?'✕':c.status==='warn'?'!':'?'}</div>
      <div class="check-title">${esc(c.title)}</div>
      ${c.severity?`<span class="sev-badge ${c.severity}">${c.severity}</span>`:''}
    </div>

    <div class="observed">${esc(c.observed||c.rationale||'—')}</div>

    ${c.expected?`<details><summary>Expected</summary><div class="detail-content">${esc(c.expected)}</div></details>`:''}
    ${c.rationale?`<details><summary>Why</summary><div class="detail-content">${esc(c.rationale)}</div></details>`:''}

    ${ev.length?`<div class="evidence-strip">${ev.map(e=>{
      if(e.kind==='image')return `<div class="ev-item image" onclick="openLb('${e.url}','image','${esc(e.label||'')}')"><img src="${e.url}" alt="${esc(e.label)}"></div>`;
      if(e.kind==='video')return `<div class="ev-item video" onclick="openLb('${e.url}','video','${esc(e.label||'')}')"><div class="ev-label">${esc(e.label||e.kind)}</div></div>`;
      return `<div class="ev-item file" onclick="openLb('${e.url}','file','${esc(e.label||'')}')">${esc(e.label||e.kind)}</div>`;
    }).join('')}</div>`:'<div style="color:var(--muted);font-size:13px;margin-bottom:16px">No visual evidence attached</div>'}

    <div class="decisions">
      <button class="btn-decide btn-accept" onclick="decide('accepted')">✓ Accept</button>
      <button class="btn-decide btn-reject" onclick="decide('rejected')">✕ Reject</button>
      <button class="btn-decide btn-skip" onclick="next()">Skip →</button>
    </div>
    <div class="kbd-hint">
      <span class="kbd">A</span> accept &nbsp;
      <span class="kbd">R</span> reject &nbsp;
      <span class="kbd">Space</span> skip
    </div>
  </div>`;
  updateProgress();
}

async function decide(d){
  if(!report)return;
  const checks=report.checks||[];
  if(currentIdx>=checks.length)return;
  const c=checks[currentIdx];
  decisions[c.check_id]=d;

  // Animate out
  const card=document.getElementById('checkCard');
  if(card)card.classList.add('deciding');

  // Send to server
  fetch(`/api/reports/${report.report_id}/checks/${c.check_id}`,{
    method:'PATCH',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({editable:{human_decision:d}})
  });

  setTimeout(()=>{currentIdx++;renderCheck();},200);
}

function next(){currentIdx++;renderCheck();}

function openLb(url,kind,label){
  const lb=document.getElementById('lightbox');
  if(kind==='image')lb.innerHTML=`<img src="${url}" alt="${esc(label)}">`;
  else if(kind==='video')lb.innerHTML=`<video controls autoplay src="${url}"></video>`;
  else{lb.innerHTML='<pre id="lbp">Loading...</pre>';fetch(url).then(r=>r.text()).then(t=>{try{document.getElementById('lbp').textContent=JSON.stringify(JSON.parse(t),null,2)}catch{document.getElementById('lbp').textContent=t}});}
  lb.classList.add('show');
}

// Keyboard shortcuts
document.addEventListener('keydown',e=>{
  if(!report||document.getElementById('lightbox').classList.contains('show'))return;
  if(e.target.tagName==='SELECT'||e.target.tagName==='INPUT')return;
  if(e.key==='a'||e.key==='A')decide('accepted');
  else if(e.key==='r'||e.key==='R')decide('rejected');
  else if(e.key===' ') {e.preventDefault();next();}
});

async function loadReportList(){
  const r=await fetch('/api/reports');
  if(r.ok){const ids=await r.json();const sel=document.getElementById('reportSelect');
    sel.innerHTML='<option value="">Select report...</option>';
    for(const id of ids){const o=document.createElement('option');o.value=id;o.textContent=id;sel.appendChild(o);}
  }
}
async function loadReport(id){
  if(!id)return;
  const r=await fetch(`/api/reports/${id}`);
  if(r.ok){report=await r.json();currentIdx=0;decisions={};renderCheck();}
}

async function main(){
  await loadReportList();
  const ws=new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage=(e)=>{
    const evt=JSON.parse(e.data);
    if(evt.event_type==='report.replaced'&&evt.payload.report){
      report=evt.payload.report;currentIdx=0;decisions={};renderCheck();
    }else if(evt.event_type==='report.list_changed'){loadReportList();}
  };
}
main();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return PAGE

@app.get("/api/reports")
async def list_reports():
    return sorted(REPORTS.keys())

@app.get("/api/reports/{rid}")
async def get_report(rid: str):
    if rid not in REPORTS:
        return JSONResponse({"error": "not found"}, status_code=404)
    return REPORTS[rid]

@app.post("/api/reports")
async def create_report(report: dict = Body(...)):
    rid = report.get("report_id", f"rpt_{int(time.time())}")
    report["report_id"] = rid
    REPORTS[rid] = report
    await broadcast({"event_type": "report.replaced", "payload": {"report": report}})
    await broadcast({"event_type": "report.list_changed", "payload": {}})
    return {"ok": True, "report_id": rid}

@app.patch("/api/reports/{rid}/checks/{cid}")
async def patch_check(rid: str, cid: str, patch: dict = Body(...)):
    if rid not in REPORTS:
        return JSONResponse({"error": "not found"}, status_code=404)
    for chk in REPORTS[rid].get("checks", []):
        if chk.get("check_id") == cid:
            if "editable" in patch and "editable" in chk:
                chk["editable"].update(patch["editable"])
            else:
                chk.update(patch)
            break
    await broadcast({"event_type": "check.updated", "payload": {"check_id": cid, "patch": patch}})
    return {"ok": True}

@app.patch("/api/reports/{rid}/summary")
async def patch_summary(rid: str, patch: dict = Body(...)):
    REPORTS.setdefault(rid, {}).setdefault("summary", {}).update(patch)
    await broadcast({"event_type": "summary.updated", "payload": {"patch": patch}})
    return {"ok": True}

@app.post("/api/attachments/{eid}")
async def upload_attachment(eid: str, file: UploadFile = File(...)):
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix if file.filename else ".bin"
    dest = ATTACHMENTS_DIR / f"{eid}{ext}"
    content = await file.read()
    dest.write_bytes(content)
    ATTACHMENTS[eid] = dest
    return JSONResponse({"ok": True, "sha256": hashlib.sha256(content).hexdigest(), "url": f"/attachments/{eid}"})

@app.get("/attachments/{eid}")
async def get_attachment(eid: str):
    if eid in ATTACHMENTS:
        return FileResponse(ATTACHMENTS[eid])
    for rpt in REPORTS.values():
        for ev in rpt.get("evidence", []):
            if ev.get("evidence_id") == eid:
                url = ev.get("url", "")
                if url.startswith("/"):
                    p = ROOT / url.lstrip("/")
                    if p.exists():
                        return FileResponse(p)
    return JSONResponse({"error": "not found"}, status_code=404)

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    CLIENTS.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in CLIENTS:
            CLIENTS.remove(ws)

def main():
    port = 8420
    for i, a in enumerate(sys.argv[1:]):
        if a == "--port" and i + 2 <= len(sys.argv):
            port = int(sys.argv[i + 2])
    print(f"Evidence Review: http://127.0.0.1:{port}/")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

if __name__ == "__main__":
    main()
