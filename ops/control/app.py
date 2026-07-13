"""TTS control plane — runs on the NAS (always on), the GPU box polls it.

Why pull, not push: the box is frequently off (repairs, reboots, no LAN). The
agent reaches *out* to this service, so the box needs no inbound ports and the
queue simply waits while it's down. You can enqueue work from a phone; the box
picks it up whenever it comes back.

The GPU is a single exclusive resource, so `device=gpu` jobs are handed out one
at a time. `device=cpu` jobs (probe renders) run in parallel — that is what lets
you listen to samples *without killing a training run*, which is the single
biggest workflow pain this replaces.

Auth: a shared token (X-Token). Deployment is on a tailnet, so this is a guard
against accidents, not a hardened boundary.
"""
import json
import os
import time
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db import DB
from notify import tg, wake_on_lan

DATA = Path(os.environ.get("TTS_DATA", "/data"))
TOKEN = os.environ.get("TTS_TOKEN", "change-me")
BOX_MAC = os.environ.get("BOX_MAC", "")
BOX_BROADCAST = os.environ.get("BOX_BROADCAST", "255.255.255.255")
OFFLINE_AFTER = int(os.environ.get("OFFLINE_AFTER_SEC", "180"))
DISK_WARN_GB = float(os.environ.get("DISK_WARN_GB", "50"))

LOGS = DATA / "logs"
SAMPLES = DATA / "samples"
for d in (LOGS, SAMPLES):
    d.mkdir(parents=True, exist_ok=True)

db = DB(DATA / "app.sqlite")
app = FastAPI(title="TTS control plane")

# Alert de-duplication: we only want ONE "box offline" message, not one per tick.
_alerted = {"offline": False, "disk": False}


def auth(x_token: str = Header(default="")):
    if x_token != TOKEN:
        raise HTTPException(401, "bad token")
    return True


# ---------------------------------------------------------------- agent API

class Heartbeat(BaseModel):
    host: str = "win-train"
    gpu_used_mb: Optional[int] = None
    gpu_free_mb: Optional[int] = None
    disk_free_gb: Optional[float] = None
    running_jobs: List[int] = []
    meta: dict = {}


@app.post("/api/heartbeat", dependencies=[Depends(auth)])
def heartbeat(hb: Heartbeat):
    db.heartbeat(hb.host, hb.gpu_used_mb, hb.gpu_free_mb, hb.disk_free_gb,
                 hb.running_jobs, hb.meta)
    if _alerted["offline"]:
        _alerted["offline"] = False
        tg(f"✅ <b>{hb.host} is back online</b>")
    if hb.disk_free_gb is not None:
        if hb.disk_free_gb < DISK_WARN_GB and not _alerted["disk"]:
            _alerted["disk"] = True
            tg(f"⚠️ <b>Low disk on {hb.host}</b>: {hb.disk_free_gb:.0f} GB free")
        elif hb.disk_free_gb >= DISK_WARN_GB:
            _alerted["disk"] = False
    # tell the agent which of its jobs were asked to stop
    canceled = [r["id"] for r in db.q(
        "SELECT id FROM jobs WHERE cancel=1 AND status='running'")]
    return {"ok": True, "cancel": canceled}


@app.get("/api/jobs/next", dependencies=[Depends(auth)])
def next_job(device: str = "gpu"):
    job = db.claim_next(device, db.gpu_busy())
    if not job:
        return {"job": None}
    tg(f"▶️ <b>Job {job['id']} started</b> — {job['type']} ({device})")
    return {"job": _job_out(job)}


class Progress(BaseModel):
    progress: dict = {}
    log: str = ""


@app.post("/api/jobs/{job_id}/progress", dependencies=[Depends(auth)])
def job_progress(job_id: int, p: Progress):
    if p.progress:
        db.set_progress(job_id, p.progress)
    if p.log:
        with (LOGS / f"{job_id}.log").open("a", encoding="utf-8") as f:
            f.write(p.log)
    return {"ok": True}


class Done(BaseModel):
    status: str = "done"          # done | failed
    error: Optional[str] = None


@app.post("/api/jobs/{job_id}/done", dependencies=[Depends(auth)])
def job_done(job_id: int, d: Done):
    db.finish(job_id, d.status, d.error)
    job = db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
    icon = "✅" if d.status == "done" else "❌"
    msg = f"{icon} <b>Job {job_id} {d.status}</b> — {job['type'] if job else '?'}"
    if d.error:
        msg += f"\n<code>{d.error[:400]}</code>"
    tg(msg)
    return {"ok": True}


class CheckpointIn(BaseModel):
    run: str
    epoch: Optional[int] = None
    path: str
    size_bytes: Optional[int] = None


@app.post("/api/checkpoints", dependencies=[Depends(auth)])
def add_checkpoint(c: CheckpointIn):
    """Agent registers a checkpoint it just saved (it stays ON THE BOX — 2 GB
    each; we track metadata, and optionally auto-render probes from it)."""
    try:
        cid = db.x(
            "INSERT OR IGNORE INTO checkpoints(run, epoch, path, size_bytes, created_at) "
            "VALUES(?,?,?,?,?)", (c.run, c.epoch, c.path, c.size_bytes, time.time()))
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "id": cid}


@app.post("/api/samples", dependencies=[Depends(auth)])
async def upload_sample(
    run: str = Form(...),
    probe_set: str = Form(...),
    epoch: Optional[int] = Form(None),
    job_id: Optional[int] = Form(None),
    params: str = Form("{}"),
    files: List[UploadFile] = File(...),
):
    """Agent uploads rendered probe wavs. These are small and land on the NAS —
    so you can listen from a phone even when the box is off (or in repair)."""
    rel = f"{run}/e{epoch if epoch is not None else 0}/{probe_set}"
    out = SAMPLES / rel
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(files, key=lambda x: x.filename or ""):
        name = Path(f.filename or f"{n:02d}.wav").name
        (out / name).write_bytes(await f.read())
        n += 1
    sid = db.x(
        "INSERT INTO samples(job_id, run, epoch, probe_set, params, rel_dir, n_clips, created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (job_id, run, epoch, probe_set, params, rel, n, time.time()))
    tg(f"🎧 <b>New samples</b> — {run} e{epoch} / {probe_set} ({n} clips)")
    return {"ok": True, "sample_id": sid, "n": n}


# ---------------------------------------------------------------- UI API

def _job_out(j):
    j = dict(j)
    j["params"] = json.loads(j.get("params") or "{}")
    j["progress"] = json.loads(j.get("progress") or "{}")
    return j


@app.get("/api/status")
def status():
    hb = db.last_heartbeat()
    age = (time.time() - hb["ts"]) if hb else None
    online = age is not None and age < OFFLINE_AFTER
    return {
        "online": online,
        "last_seen_sec": age,
        "heartbeat": hb,
        "running": [_job_out(j) for j in db.running_jobs()],
        "queued": db.q("SELECT COUNT(*) AS n FROM jobs WHERE status='queued'")[0]["n"],
        "gpu_busy": db.gpu_busy(),
    }


class JobIn(BaseModel):
    type: str
    params: dict = {}
    device: str = "gpu"
    priority: int = 0


ALLOWED = {"train_st2", "synth_st2", "recut_24k", "audit"}


@app.post("/api/jobs")
def create_job(j: JobIn):
    if j.type not in ALLOWED:
        raise HTTPException(400, f"unknown job type: {j.type}")
    if j.device not in ("gpu", "cpu"):
        raise HTTPException(400, "device must be gpu|cpu")
    jid = db.enqueue(j.type, j.params, j.device, j.priority)
    return {"ok": True, "id": jid}


@app.get("/api/jobs")
def list_jobs(limit: int = 50):
    return {"jobs": [_job_out(j) for j in db.q(
        "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,))]}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    job = db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if not job:
        raise HTTPException(404, "no such job")
    if job["status"] == "queued":
        db.finish(job_id, "canceled")
    else:
        db.x("UPDATE jobs SET cancel=1 WHERE id=?", (job_id,))
    return {"ok": True}


@app.get("/api/jobs/{job_id}/log", response_class=PlainTextResponse)
def job_log(job_id: int, lines: int = 200):
    p = LOGS / f"{job_id}.log"
    if not p.exists():
        return ""
    tail = p.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    return "\n".join(tail)


@app.get("/api/checkpoints")
def list_checkpoints(run: Optional[str] = None):
    if run:
        rows = db.q("SELECT * FROM checkpoints WHERE run=? ORDER BY epoch DESC", (run,))
    else:
        rows = db.q("SELECT * FROM checkpoints ORDER BY id DESC LIMIT 100")
    return {"checkpoints": rows}


@app.get("/api/samples")
def list_samples(limit: int = 50):
    rows = db.q("SELECT * FROM samples ORDER BY id DESC LIMIT ?", (limit,))
    for r in rows:
        r["params"] = json.loads(r.get("params") or "{}")
        r["verdicts"] = db.q(
            "SELECT clip_idx, verdict, comment FROM verdicts WHERE sample_id=?", (r["id"],))
    return {"samples": rows}


class VerdictIn(BaseModel):
    sample_id: int
    clip_idx: int
    verdict: Optional[str] = None       # ok | bad
    comment: Optional[str] = None


@app.post("/api/verdicts")
def set_verdict(v: VerdictIn):
    db.x(
        "INSERT INTO verdicts(sample_id, clip_idx, verdict, comment, created_at) "
        "VALUES(?,?,?,?,?) ON CONFLICT(sample_id, clip_idx) "
        "DO UPDATE SET verdict=excluded.verdict, comment=excluded.comment",
        (v.sample_id, v.clip_idx, v.verdict, v.comment, time.time()))
    return {"ok": True}


@app.post("/api/wol")
def wol():
    if not BOX_MAC:
        raise HTTPException(400, "BOX_MAC not configured")
    wake_on_lan(BOX_MAC, BOX_BROADCAST)
    tg("⏰ <b>Wake-on-LAN sent</b> to the GPU box")
    return {"ok": True}


@app.get("/media/{path:path}")
def media(path: str):
    """Serve a rendered wav (players in the UI point here)."""
    p = (SAMPLES / path).resolve()
    if not str(p).startswith(str(SAMPLES.resolve())) or not p.is_file():
        raise HTTPException(404, "not found")
    return FileResponse(p)


# ---------------------------------------------------------------- watchdog

@app.on_event("startup")
async def watchdog():
    import asyncio

    async def loop():
        while True:
            try:
                hb = db.last_heartbeat()
                stale = (not hb) or (time.time() - hb["ts"] > OFFLINE_AFTER)
                # Only shout if the box vanished *while it still owed us work* —
                # a box that's simply off with an empty queue is not an incident.
                if stale and db.running_jobs() and not _alerted["offline"]:
                    _alerted["offline"] = True
                    tg("🔴 <b>GPU box went offline</b> with jobs still running.")
                db.prune_heartbeats()
            except Exception:
                pass
            await asyncio.sleep(60)

    asyncio.create_task(loop())


app.mount("/", StaticFiles(directory=str(Path(__file__).parent / "static"), html=True))
