#!/usr/bin/env python3
"""Local-host interactive evidence review tool for AI-generated pass/fail reports.

The agent pushes structured reports + evidence (screenshots, logs, diffs) to this
server via HTTP. The browser renders an interactive triage layout with live WebSocket
updates. The human reviews, edits triage fields, and submits decisions.

Usage:
  python3 tools/review_server.py [--port 8420] [--reports-dir qa_runs]
  Then open http://127.0.0.1:8420/ in the browser.

The agent pushes reports via:
  POST /api/reports     — create/replace a report
  PATCH /api/reports/{id}/checks/{check_id} — update a check
  PATCH /api/reports/{id}/summary — update summary
  POST /api/attachments — upload a file (screenshot, log, etc.)
"""
from __future__ import annotations

import json
import os
import sys
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS_DIR = ROOT / "qa_runs" / "review_reports"
DEFAULT_ATTACHMENTS_DIR = ROOT / "qa_runs" / "review_attachments"

app = FastAPI(title="Just Dodge Evidence Review Tool")

# In-memory stores (local tool, single-user)
REPORTS: dict[str, dict[str, Any]] = {}
ATTACHMENTS: dict[str, Path] = {}
CLIENTS: list[WebSocket] = []
EVENT_LOG: list[str] = []


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_log(msg: str) -> None:
    global EVENT_LOG
    ts = datetime.now().strftime("%H:%M:%S")
    EVENT_LOG.append(f"[{ts}] {msg}")
    if len(EVENT_LOG) > 200:
        EVENT_LOG[:] = EVENT_LOG[-200:]


async def broadcast(message: dict[str, Any]) -> None:
    living = []
    for ws in CLIENTS:
        try:
            await ws.send_json(message)
            living.append(ws)
        except Exception:
            pass
    CLIENTS[:] = living


# ── HTML page ──────────────────────────────────────────────────────────────

HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Just Dodge Evidence Review</title>
<style>
:root {
  --bg: #0f1115; --panel: #171a21; --panel2: #1c2030; --line: #2b3240;
  --text: #e8edf5; --muted: #9eacc0; --accent: #58a6ff;
  --pass: #3ddc97; --fail: #ff5d5d; --warn: #ffb020; --pending: #8b949e;
}
* { box-sizing: border-box; }
body { margin:0; font:14px/1.45 system-ui,sans-serif; background:var(--bg); color:var(--text); }
.topbar { padding:10px 16px; border-bottom:1px solid var(--line); background:var(--panel);
  display:flex; gap:16px; align-items:center; flex-wrap:wrap; }
.app { display:grid; grid-template-columns: 280px 1fr 1fr; height:calc(100vh - 52px); }
.sidebar, .findings, .evidence { overflow:auto; padding:12px; border-right:1px solid var(--line); }
.evidence { border-right:0; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px; margin-bottom:10px; cursor:pointer; transition:border-color .15s; }
.card:hover { border-color:var(--accent); }
.card.selected { border-color:var(--accent); background:var(--panel2); }
.meta { color:var(--muted); font-size:12px; }
.pill { padding:3px 10px; border-radius:999px; font-weight:700; font-size:12px; display:inline-block; }
.pill.pass { background:var(--pass); color:#003; }
.pill.fail { background:var(--fail); color:#fff; }
.pill.warn { background:var(--warn); color:#220; }
.pill.pending { background:var(--pending); color:#fff; }
.status-pass { color:var(--pass); }
.status-fail { color:var(--fail); }
.status-warn { color:var(--warn); }
.status-pending { color:var(--pending); }
input, select, textarea { width:100%; background:var(--bg); color:var(--text);
  border:1px solid var(--line); border-radius:8px; padding:8px; font-size:13px; }
input:focus, select:focus, textarea:focus { outline:none; border-color:var(--accent); }
.btn { background:var(--accent); color:#fff; border:none; border-radius:8px; padding:8px 16px; cursor:pointer; font-size:13px; }
.btn:hover { opacity:0.85; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
details { border:1px solid var(--line); border-radius:8px; padding:8px; margin-top:8px; background:rgba(255,255,255,0.02); }
summary { cursor:pointer; font-weight:600; }
pre { white-space:pre-wrap; background:#0c0e12; padding:10px; border-radius:8px; border:1px solid var(--line); font-size:12px; max-height:300px; overflow:auto; }
img.evidence-img { max-width:100%; border-radius:8px; border:1px solid var(--line); }
.filter-row { display:flex; gap:8px; align-items:center; margin-bottom:8px; flex-wrap:wrap; }
.tab { padding:6px 12px; border-radius:6px; cursor:pointer; background:var(--panel2); border:1px solid var(--line); font-size:12px; }
.tab.active { background:var(--accent); color:#fff; border-color:var(--accent); }
.report-selector { background:var(--panel2); border:1px solid var(--line); border-radius:8px; padding:6px; color:var(--text); font-size:13px; }
.empty { color:var(--muted); text-align:center; padding:40px; }
.evidence-link { color:var(--accent); text-decoration:none; }
.evidence-link:hover { text-decoration:underline; }
</style>
</head>
<body>
<div class="topbar">
  <select id="reportSelect" class="report-selector" onchange="loadReport(this.value)">
    <option value="">— Select report —</option>
  </select>
  <div id="buildInfo" class="meta">No report loaded</div>
  <div id="gatePill" class="pill pending">PENDING</div>
  <div id="counts" class="meta"></div>
  <div style="margin-left:auto">
    <span id="wsStatus" class="meta">connecting...</span>
  </div>
</div>

<div class="app">
  <div class="sidebar">
    <div class="filter-row">
      <input id="searchInput" placeholder="Search checks..." oninput="renderChecks()" style="flex:1"/>
    </div>
    <div class="filter-row">
      <label class="meta"><input type="checkbox" id="filterFail" onchange="renderChecks()"> Fail only</label>
      <label class="meta"><input type="checkbox" id="filterPending" onchange="renderChecks()"> Needs review</label>
    </div>
    <div id="checksList"></div>
  </div>

  <div class="findings">
    <div id="detailPanel" class="empty">Select a check from the left.</div>
  </div>

  <div class="evidence">
    <div class="filter-row" id="evidenceTabs"></div>
    <div id="evidencePanel" class="empty">No evidence selected.</div>
    <details open style="margin-top:12px">
      <summary>Agent Event Log</summary>
      <pre id="eventLog"></pre>
    </details>
  </div>
</div>

<script>
let report = null;
let selectedCheckId = null;
let activeEvidenceTab = 'all';

function escapeHtml(s) {
  if (!s) return '';
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function renderHeader() {
  if (!report) return;
  document.getElementById('buildInfo').textContent =
    `${report.run?.project || 'Just Dodge'} · ${report.run?.branch || ''} · ${report.run?.commit || ''}`;
  const gate = document.getElementById('gatePill');
  const g = report.summary?.gate || 'pending';
  gate.textContent = g.toUpperCase();
  gate.className = `pill ${g}`;
  document.getElementById('counts').textContent =
    `Pass ${report.summary?.pass_count||0} · Fail ${report.summary?.fail_count||0} · Warn ${report.summary?.warning_count||0}`;
}

function renderChecks() {
  const root = document.getElementById('checksList');
  root.innerHTML = '';
  if (!report) return;
  const search = document.getElementById('searchInput').value.toLowerCase();
  const failOnly = document.getElementById('filterFail').checked;
  const pendingOnly = document.getElementById('filterPending').checked;
  for (const c of report.checks) {
    if (search && !c.title.toLowerCase().includes(search) && !c.category.toLowerCase().includes(search)) continue;
    if (failOnly && c.status !== 'fail') continue;
    if (pendingOnly && c.editable?.human_decision !== 'pending') continue;
    const el = document.createElement('div');
    el.className = 'card' + (c.check_id === selectedCheckId ? ' selected' : '');
    const sc = c.editable?.human_decision || c.status;
    el.innerHTML = `
      <div><strong>${escapeHtml(c.title)}</strong></div>
      <div class="meta">${escapeHtml(c.category)} · ${escapeHtml(c.severity||'')}</div>
      <div class="status-${c.status}">${c.status.toUpperCase()}</div>`;
    el.onclick = () => { selectedCheckId = c.check_id; renderDetail(); renderChecks(); };
    root.appendChild(el);
  }
}

function renderDetail() {
  const root = document.getElementById('detailPanel');
  root.className = '';
  if (!report || !selectedCheckId) { root.className='empty'; root.textContent='Select a check.'; return; }
  const c = report.checks.find(x => x.check_id === selectedCheckId);
  if (!c) { root.className='empty'; root.textContent='Check not found.'; return; }

  // Evidence tabs
  const tabsEl = document.getElementById('evidenceTabs');
  tabsEl.innerHTML = '';
  const evidence = (c.evidence_refs || []).map(id => report.evidence?.find(e => e.evidence_id === id)).filter(Boolean);
  if (evidence.length > 0) {
    for (const ev of evidence) {
      const tab = document.createElement('div');
      tab.className = 'tab' + (activeEvidenceTab === ev.evidence_id ? ' active' : '');
      tab.textContent = ev.label || ev.kind;
      tab.onclick = () => { activeEvidenceTab = ev.evidence_id; renderEvidence(); renderDetail(); };
      tabsEl.appendChild(tab);
    }
  }

  root.innerHTML = `
    <div class="card">
      <h2 style="margin:0 0 4px">${escapeHtml(c.title)}</h2>
      <div class="meta">${escapeHtml(c.category)} · ${escapeHtml(c.severity||'medium')} · <span class="status-${c.status}">${c.status.toUpperCase()}</span></div>
      ${c.confidence != null ? `<div class="meta">Confidence: ${(c.confidence*100).toFixed(0)}%</div>` : ''}
    </div>
    <div class="card">
      <h3>Expected</h3><p>${escapeHtml(c.expected||'—')}</p>
      <h3>Observed</h3><p>${escapeHtml(c.observed||'—')}</p>
      <h3>Rationale</h3><p>${escapeHtml(c.rationale||'—')}</p>
    </div>
    <div class="card">
      <h3>Triage (editable)</h3>
      <div class="grid2">
        <div><label class="meta">Human decision</label>
          <select id="edit-decision">
            <option value="pending" ${c.editable?.human_decision==='pending'?'selected':''}>Pending</option>
            <option value="accepted" ${c.editable?.human_decision==='accepted'?'selected':''}>Accepted</option>
            <option value="rejected" ${c.editable?.human_decision==='rejected'?'selected':''}>Rejected</option>
            <option value="false_positive" ${c.editable?.human_decision==='false_positive'?'selected':''}>False Positive</option>
          </select>
        </div>
        <div><label class="meta">Release blocker</label>
          <select id="edit-blocker">
            <option value="false" ${!c.editable?.release_blocker?'selected':''}>No</option>
            <option value="true" ${c.editable?.release_blocker?'selected':''}>Yes</option>
          </select>
        </div>
      </div>
      <div style="margin-top:8px">
        <label class="meta">Reviewer note</label>
        <textarea id="edit-note" rows="3">${escapeHtml(c.editable?.reviewer_note||'')}</textarea>
      </div>
      <div style="margin-top:8px">
        <button class="btn" onclick="saveEdit()">Save decision</button>
        <span id="saveStatus" class="meta"></span>
      </div>
    </div>
    ${evidence.length > 0 ? `<div class="card"><h3>Evidence (${evidence.length})</h3><div id="evidenceLinks"></div></div>` : ''}
  `;
  if (evidence.length > 0) {
    const linksEl = document.getElementById('evidenceLinks');
    for (const ev of evidence) {
      const a = document.createElement('a');
      a.className = 'evidence-link';
      a.href = '#';
      a.textContent = `${ev.label || ev.kind} (${ev.kind})`;
      a.onclick = (e) => { e.preventDefault(); activeEvidenceTab = ev.evidence_id; renderEvidence(); };
      a.style.display = 'block';
      linksEl.appendChild(a);
    }
  }
}

function renderEvidence() {
  const root = document.getElementById('evidencePanel');
  root.className = '';
  if (!report || !selectedCheckId || activeEvidenceTab === 'all') {
    root.className = 'empty'; root.textContent = 'Select evidence from the tabs above.'; return;
  }
  const c = report.checks.find(x => x.check_id === selectedCheckId);
  const ev = report.evidence?.find(e => e.evidence_id === activeEvidenceTab);
  if (!ev) { root.className='empty'; root.textContent='Evidence not found.'; return; }
  if (ev.kind === 'image') {
    root.innerHTML = `<img class="evidence-img" src="${ev.url}" alt="${escapeHtml(ev.label||'')}"/>`;
  } else if (ev.kind === 'video') {
    root.innerHTML = `<video controls style="max-width:100%;border-radius:8px;border:1px solid var(--line)" src="${ev.url}"></video>`;
  } else if (ev.kind === 'log' || ev.kind === 'json' || ev.kind === 'diff') {
    root.innerHTML = `<pre id="evidenceText">Loading...</pre>`;
    fetch(ev.url).then(r => r.text()).then(t => {
      document.getElementById('evidenceText').textContent = t;
    });
  } else {
    root.innerHTML = `<a class="evidence-link" href="${ev.url}" target="_blank">Open ${escapeHtml(ev.label||ev.kind)}</a>`;
  }
}

async function saveEdit() {
  if (!report || !selectedCheckId) return;
  const patch = {
    editable: {
      human_decision: document.getElementById('edit-decision').value,
      release_blocker: document.getElementById('edit-blocker').value === 'true',
      reviewer_note: document.getElementById('edit-note').value,
    }
  };
  document.getElementById('saveStatus').textContent = 'Saving...';
  const res = await fetch(`/api/reports/${report.report_id}/checks/${selectedCheckId}`, {
    method: 'PATCH', headers: {'Content-Type':'application/json'}, body: JSON.stringify(patch)
  });
  if (res.ok) {
    document.getElementById('saveStatus').textContent = 'Saved ✓';
    const c = report.checks.find(x => x.check_id === selectedCheckId);
    if (c) c.editable = {...c.editable, ...patch.editable};
  } else {
    document.getElementById('saveStatus').textContent = 'Save failed';
  }
  setTimeout(() => { document.getElementById('saveStatus').textContent=''; }, 2000);
}

function appendLog(msg) {
  const log = document.getElementById('eventLog');
  log.textContent = `[${new Date().toLocaleTimeString()}] ${msg}\\n` + log.textContent;
}

async function loadReportList() {
  const res = await fetch('/api/reports');
  if (res.ok) {
    const ids = await res.json();
    const sel = document.getElementById('reportSelect');
    sel.innerHTML = '<option value="">— Select report —</option>';
    for (const id of ids) {
      const opt = document.createElement('option');
      opt.value = id; opt.textContent = id;
      sel.appendChild(opt);
    }
  }
}

async function loadReport(id) {
  if (!id) return;
  const res = await fetch(`/api/reports/${id}`);
  if (res.ok) {
    report = await res.json();
    selectedCheckId = null; activeEvidenceTab = 'all';
    renderHeader(); renderChecks();
    document.getElementById('detailPanel').className='empty';
    document.getElementById('detailPanel').textContent='Select a check.';
    document.getElementById('evidencePanel').className='empty';
    document.getElementById('evidencePanel').textContent='No evidence selected.';
  }
}

async function main() {
  await loadReportList();
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => { document.getElementById('wsStatus').textContent='live'; };
  ws.onclose = () => { document.getElementById('wsStatus').textContent='disconnected'; };
  ws.onmessage = (evt) => {
    const event = JSON.parse(evt.data);
    appendLog(`${event.event_type}: ${JSON.stringify(event.payload||{}).slice(0,200)}`);
    if (event.event_type === 'report.replaced' && event.payload.report) {
      report = event.payload.report;
      renderHeader(); renderChecks(); renderDetail();
    } else if (event.event_type === 'check.updated' && report) {
      const idx = report.checks.findIndex(x => x.check_id === event.payload.check_id);
      if (idx >= 0) { report.checks[idx] = {...report.checks[idx], ...event.payload.patch}; }
      renderChecks(); renderDetail();
    } else if (event.event_type === 'summary.updated' && report) {
      report.summary = {...report.summary, ...event.payload.patch};
      renderHeader();
    } else if (event.event_type === 'report.list_changed') {
      loadReportList();
    }
  };
}
main();
</script>
</body>
</html>
"""


# ── API routes ─────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return HTML_PAGE


@app.get("/api/reports")
async def list_reports() -> list[str]:
    return sorted(REPORTS.keys())


@app.get("/api/reports/{report_id}")
async def get_report(report_id: str) -> dict[str, Any]:
    if report_id not in REPORTS:
        return JSONResponse({"error": "not found"}, status_code=404)
    return REPORTS[report_id]


@app.post("/api/reports")
async def create_report(report: dict[str, Any] = Body(...)) -> dict[str, Any]:
    rid = report.get("report_id", f"rpt_{int(time.time())}")
    report["report_id"] = rid
    report["version"] = report.get("version", 1)
    REPORTS[rid] = report
    append_log(f"Report created: {rid}")
    await broadcast({"event_type": "report.replaced", "payload": {"report": report}, "sent_at": now_iso()})
    await broadcast({"event_type": "report.list_changed", "payload": {}, "sent_at": now_iso()})
    return {"ok": True, "report_id": rid}


@app.patch("/api/reports/{report_id}/checks/{check_id}")
async def patch_check(report_id: str, check_id: str, patch: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if report_id not in REPORTS:
        return JSONResponse({"error": "not found"}, status_code=404)
    for chk in REPORTS[report_id].get("checks", []):
        if chk.get("check_id") == check_id:
            # Deep merge for editable sub-dict
            if "editable" in patch and "editable" in chk:
                chk["editable"].update(patch["editable"])
            else:
                chk.update(patch)
            break
    REPORTS[report_id]["version"] = REPORTS[report_id].get("version", 1) + 1
    await broadcast({
        "event_type": "check.updated",
        "payload": {"check_id": check_id, "patch": patch},
        "sent_at": now_iso(),
    })
    return {"ok": True}


@app.patch("/api/reports/{report_id}/summary")
async def patch_summary(report_id: str, patch: dict[str, Any] = Body(...)) -> dict[str, Any]:
    if report_id not in REPORTS:
        return JSONResponse({"error": "not found"}, status_code=404)
    REPORTS[report_id].setdefault("summary", {}).update(patch)
    await broadcast({"event_type": "summary.updated", "payload": {"patch": patch}, "sent_at": now_iso()})
    return {"ok": True}


@app.post("/api/attachments/{evidence_id}")
async def upload_attachment(evidence_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    DEFAULT_ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = DEFAULT_ATTACHMENTS_DIR / f"{evidence_id}_{file.filename}"
    content = await file.read()
    dest.write_bytes(content)
    ATTACHMENTS[evidence_id] = dest
    sha = hashlib.sha256(content).hexdigest()
    append_log(f"Attachment uploaded: {evidence_id} ({len(content)} bytes, sha256={sha[:16]})")
    return JSONResponse({"ok": True, "evidence_id": evidence_id, "sha256": sha, "url": f"/attachments/{evidence_id}"})


@app.get("/attachments/{evidence_id}")
async def get_attachment(evidence_id: str):
    if evidence_id not in ATTACHMENTS:
        # Try to resolve from evidence refs in reports
        for report in REPORTS.values():
            for ev in report.get("evidence", []):
                if ev.get("evidence_id") == evidence_id:
                    url = ev.get("url", "")
                    if url.startswith("/"):
                        p = ROOT / url.lstrip("/")
                        if p.exists():
                            return FileResponse(p)
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(ATTACHMENTS[evidence_id])


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    CLIENTS.append(websocket)
    append_log("WebSocket client connected")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in CLIENTS:
            CLIENTS.remove(websocket)
        append_log("WebSocket client disconnected")


# ── CLI ────────────────────────────────────────────────────────────────────


def main() -> None:
    port = 8420
    host = "127.0.0.1"
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--port" and i + 2 <= len(sys.argv):
            port = int(sys.argv[i + 2])
        elif arg == "--host":
            host = sys.argv[i + 2] if i + 2 <= len(sys.argv) else "127.0.0.1"

    print(f"Evidence Review Tool starting on http://{host}:{port}/")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
