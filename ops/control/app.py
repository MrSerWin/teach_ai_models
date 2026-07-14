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
from datetime import datetime, timedelta
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
# TV recording reminders (Telegram): how long before start / before end to ping.
TV_NOTIFY_LEAD_START = int(os.environ.get("TV_NOTIFY_LEAD_START_SEC", "600"))   # ~10 min
TV_NOTIFY_LEAD_END = int(os.environ.get("TV_NOTIFY_LEAD_END_SEC", "300"))       # ~5 min
DASH_URL = os.environ.get("DASH_URL", "")   # optional link included in reminders

LOGS = DATA / "logs"
SAMPLES = DATA / "samples"
SHOTS = DATA / "shots"          # latest live-preview frame per TV recording job
PREVIEWS = DATA / "previews"     # latest on-demand live frame per channel (atr/millet)
for d in (LOGS, SAMPLES, SHOTS, PREVIEWS):
    d.mkdir(parents=True, exist_ok=True)

# On-demand stream preview: the dashboard "pings" while its Превью tab is open;
# the agent only grabs live frames while previews are wanted, so we don't run
# ffmpeg 24/7 for nobody. A ping keeps previews alive for PREVIEW_TTL seconds.
PREVIEW_TTL = int(os.environ.get("TV_PREVIEW_TTL_SEC", "150"))
_preview_wanted_until = 0.0
TV_CHANNELS = ("atr", "millet")

# TV recordings live on their own NAS volume, written by the tv-agent. Mount the
# same host dir here (docker-compose: /volume1/tv/recordings:/recordings) so the
# dashboard can preview / download / delete finished recordings. The tv-agent
# stores files under this same path, so job.progress.file resolves 1:1.
RECORDINGS = Path(os.environ.get("TV_RECORDINGS", "/recordings"))
# Forward-looking schedule snapshot written by the tv-archiver planner
# (plan_control.py) into the shared recordings volume. Read-only here: it drives
# the "Программа" view so you can see every upcoming film/cartoon and manually
# record the ones the planner won't auto-record (e.g. Russian-language on Millet).
EPG_SNAPSHOT = Path(os.environ.get("TV_EPG_SNAPSHOT", str(RECORDINGS / "epg.json")))
# Recording padding for MANUAL records started from the schedule (mirror the
# planner's defaults so a hand-picked film gets the same generous ad-overrun tail
# and minimum-window protection against an EPG gap shorter than the film itself).
TV_PAD_PRE = int(os.environ.get("TV_ARCHIVER_PAD_PRE", "120"))
TV_PAD_POST = int(os.environ.get("TV_ARCHIVER_PAD_POST", "120"))
TV_PAD_POST_FILM = int(os.environ.get("TV_ARCHIVER_PAD_POST_FILM", "1200"))
TV_FILM_MIN_MINUTES = int(os.environ.get("TV_FILM_MIN_MINUTES", "110"))

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
    # and whether anyone is watching the live preview right now (so it should
    # grab channel frames) — avoids running ffmpeg when the tab is closed.
    return {"ok": True, "cancel": canceled,
            "preview_wanted": time.time() < _preview_wanted_until}


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


@app.post("/api/jobs/{job_id}/screenshot", dependencies=[Depends(auth)])
async def upload_screenshot(job_id: int, file: UploadFile = File(...)):
    """tv-agent posts a live-preview frame while a recording runs. We keep only
    the latest frame per job (overwrite) — it's a monitor, not an archive."""
    (SHOTS / f"{job_id}.jpg").write_bytes(await file.read())
    return {"ok": True}


@app.get("/shots/{job_id}.jpg")
def screenshot(job_id: int):
    p = SHOTS / f"{job_id}.jpg"
    if not p.is_file():
        raise HTTPException(404, "no frame yet")
    return FileResponse(p)


@app.get("/api/tv/status")
def tv_status():
    """Recording box liveness + per-channel stream state, from the tv-agent's
    last heartbeat (host 'nas-tv'). Separate from the GPU box status."""
    hb = db.last_heartbeat("nas-tv")
    age = (time.time() - hb["ts"]) if hb else None
    online = age is not None and age < OFFLINE_AFTER
    meta = json.loads(hb["meta"]) if hb and hb.get("meta") else {}
    tv_jobs = db.q(
        "SELECT * FROM jobs WHERE type='record_tv' ORDER BY "
        "COALESCE(run_at, created_at) DESC LIMIT 60")
    jobs = [_job_out(j) for j in tv_jobs]
    for j in jobs:                              # annotate downloadable recordings
        j["has_file"] = (j["status"] not in ("queued", "running")
                         and _recording_path(j) is not None)
    channels = meta.get("channels", {})         # {atr:{live:bool}, millet:{...}}
    for ch in TV_CHANNELS:                       # annotate live-preview freshness
        pv = PREVIEWS / f"{ch}.jpg"
        channels.setdefault(ch, {})["preview_age_sec"] = (
            time.time() - pv.stat().st_mtime) if pv.is_file() else None
    return {
        "online": online,
        "last_seen_sec": age,
        "channels": channels,
        "preview_wanted": time.time() < _preview_wanted_until,
        "disk_free_gb": hb["disk_free_gb"] if hb else None,
        "jobs": jobs,
    }


def _recording_path(job) -> Optional[Path]:
    """Resolve a record_tv job's mp4 on disk, guarded against path traversal.

    Returns the Path only if it exists under RECORDINGS; else None.
    """
    prog = job.get("progress") if isinstance(job.get("progress"), dict) \
        else json.loads(job.get("progress") or "{}")
    f = prog.get("file")
    if not f:
        return None
    try:
        p = Path(f).resolve()
        root = RECORDINGS.resolve()
    except Exception:
        return None
    if root not in p.parents or not p.is_file():
        return None
    return p


@app.get("/tv/media/{job_id}")
def tv_media(job_id: int, download: bool = False):
    """Stream a finished recording. Inline by default (for the in-page player,
    with HTTP range/seek support); ?download=1 forces a file download."""
    job = db.one("SELECT * FROM jobs WHERE id=? AND type='record_tv'", (job_id,))
    p = _recording_path(_job_out(job)) if job else None
    if not p:
        raise HTTPException(404, "recording not found")
    if download:
        return FileResponse(p, media_type="video/mp4", filename=p.name)
    return FileResponse(p, media_type="video/mp4")   # inline, seekable


@app.get("/tv/thumb/{job_id}.jpg")
def tv_thumb(job_id: int):
    """Preview frame: the sibling .jpg saved next to the recording (durable),
    falling back to the last live frame uploaded during recording."""
    job = db.one("SELECT * FROM jobs WHERE id=? AND type='record_tv'", (job_id,))
    if job:
        p = _recording_path(_job_out(job))
        if p and p.with_suffix(".jpg").is_file():
            return FileResponse(p.with_suffix(".jpg"))
    shot = SHOTS / f"{job_id}.jpg"
    if shot.is_file():
        return FileResponse(shot)
    raise HTTPException(404, "no thumbnail")


@app.delete("/api/tv/recordings/{job_id}")
def tv_delete(job_id: int):
    """Delete a finished recording completely: remove the files (mp4 + sidecar
    .jpg/.json), the preview frame and the log, and drop the job row so it
    disappears from the list. Refuses while still recording — Stop it first."""
    job = db.one("SELECT * FROM jobs WHERE id=? AND type='record_tv'", (job_id,))
    if not job:
        raise HTTPException(404, "no such recording")
    if job["status"] == "running":
        raise HTTPException(409, "still recording — stop it first")
    p = _recording_path(_job_out(job))
    removed = []
    if p:
        for f in (p, p.with_suffix(".jpg"), p.with_suffix(".json")):
            try:
                if f.is_file():
                    f.unlink()
                    removed.append(f.name)
            except OSError as e:
                raise HTTPException(500, f"delete failed: {e}")
    for extra in (SHOTS / f"{job_id}.jpg", LOGS / f"{job_id}.log"):
        try:
            extra.unlink(missing_ok=True)
        except OSError:
            pass
    db.x("DELETE FROM jobs WHERE id=?", (job_id,))
    return {"ok": True, "removed": removed}


@app.post("/api/tv/preview/ping")
def preview_ping():
    """The dashboard calls this while the Превью tab is open, so the agent knows
    to grab live channel frames. No auth: it only sets a short 'someone is
    watching' flag, leaks nothing."""
    global _preview_wanted_until
    _preview_wanted_until = time.time() + PREVIEW_TTL
    return {"ok": True, "ttl": PREVIEW_TTL}


@app.get("/api/tv/preview/wanted")
def preview_wanted_flag():
    """The agent polls this cheaply so it can start grabbing frames within seconds
    of the tab opening (rather than waiting for its next 30 s heartbeat)."""
    return {"wanted": time.time() < _preview_wanted_until}


@app.post("/api/tv/preview/{channel}", dependencies=[Depends(auth)])
async def upload_preview(channel: str, file: UploadFile = File(...)):
    """Agent uploads a fresh live frame for a channel (on-demand preview)."""
    if channel not in TV_CHANNELS:
        raise HTTPException(400, "unknown channel")
    (PREVIEWS / f"{channel}.jpg").write_bytes(await file.read())
    return {"ok": True}


@app.get("/tv/preview/{channel}.jpg")
def get_preview(channel: str):
    if channel not in TV_CHANNELS:
        raise HTTPException(404, "unknown channel")
    p = PREVIEWS / f"{channel}.jpg"
    if not p.is_file():
        raise HTTPException(404, "no preview yet")
    return FileResponse(p, media_type="image/jpeg")


def _scheduled_map() -> dict:
    """{(channel, program_start_iso): job_id} of record_tv jobs already queued or
    running, so the guide can both flag scheduled programs AND cancel them."""
    m = {}
    for j in db.q("SELECT id, params FROM jobs WHERE type='record_tv' "
                  "AND status IN ('queued','running')"):
        try:
            p = json.loads(j["params"] or "{}")
        except (ValueError, TypeError):
            continue
        if p.get("channel") and p.get("program_start_iso"):
            m[(p["channel"], p["program_start_iso"])] = j["id"]
    return m


@app.get("/api/tv/epg")
def tv_epg():
    """The upcoming schedule of films & cartoons on both channels, written daily by
    the tv-archiver planner. Each program carries a `decision` (record / review /
    not_crh), `scheduled` = whether a record job is queued, and `job_id` to cancel
    it. This is the single schedule view — it shows both what will record and what
    won't (with a one-click record button)."""
    try:
        data = json.loads(EPG_SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"generated_at": None, "events": [], "stale": True}
    now = datetime.now().astimezone()
    smap = _scheduled_map()
    events = []
    for e in data.get("events", []):
        try:
            if datetime.fromisoformat(e["end_iso"]) <= now:
                continue                       # already finished — drop it
        except (KeyError, ValueError):
            pass
        e = dict(e)
        jid = smap.get((e.get("channel"), e.get("start_iso")))
        e["scheduled"] = jid is not None
        e["job_id"] = jid
        events.append(e)
    return {"generated_at": data.get("generated_at"), "events": events, "stale": False}


class EpgRecord(BaseModel):
    channel: str
    start_iso: str                             # must match a program in the snapshot


@app.post("/api/tv/epg/record")
def tv_epg_record(r: EpgRecord):
    """Manually queue a recording for a program shown in the schedule (e.g. a film
    the planner skipped). Looks the program up in the snapshot for its exact times,
    so the caller can't inject arbitrary windows."""
    try:
        data = json.loads(EPG_SNAPSHOT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(503, "schedule not available yet")
    prog = next((e for e in data.get("events", [])
                 if e.get("channel") == r.channel and e.get("start_iso") == r.start_iso), None)
    if not prog:
        raise HTTPException(404, "program not in schedule")
    if (r.channel, r.start_iso) in _scheduled_map():
        raise HTTPException(409, "already scheduled")
    start = datetime.fromisoformat(prog["start_iso"])
    end = datetime.fromisoformat(prog["end_iso"])
    is_film = prog.get("category") == "film"
    if is_film:                                 # min window + bigger tail (see planner)
        floor_end = start + timedelta(minutes=TV_FILM_MIN_MINUTES)
        if floor_end > end:
            end = floor_end
    pad_post = TV_PAD_POST_FILM if is_film else TV_PAD_POST
    w_start = start - timedelta(seconds=TV_PAD_PRE)
    duration_s = int((end - start).total_seconds()) + TV_PAD_PRE + pad_post
    jid = db.enqueue("record_tv", {
        "channel": r.channel,
        "title": prog.get("clean_title") or prog.get("raw_title"),
        "category": prog.get("category"),
        "duration_s": duration_s,
        "confidence": prog.get("confidence"),
        "program_start_iso": prog["start_iso"],
        "manual": True,
    }, "tv", 0, w_start.timestamp())
    return {"ok": True, "id": jid}


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
    run_at: Optional[float] = None      # epoch seconds; None = ASAP


ALLOWED = {"train_st2", "synth_st2", "recut_24k", "audit", "record_tv"}


@app.post("/api/jobs")
def create_job(j: JobIn):
    if j.type not in ALLOWED:
        raise HTTPException(400, f"unknown job type: {j.type}")
    if j.device not in ("gpu", "cpu", "tv"):
        raise HTTPException(400, "device must be gpu|cpu|tv")
    jid = db.enqueue(j.type, j.params, j.device, j.priority, j.run_at)
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

# TV reminders already sent, so we ping once (reset on restart is harmless).
_tv_notified_start: set = set()
_tv_notified_end: set = set()


def _fmt_hm(epoch):
    return datetime.fromtimestamp(epoch).strftime("%H:%M") if epoch else "?"


def _tv_reminders():
    """Ping Telegram ~10 min before a scheduled recording starts and ~5 min
    before a running one ends (ads can overrun the schedule — a heads-up lets
    you check the stream and extend/re-record if the film is still on)."""
    now = time.time()
    link = f"\n{DASH_URL}" if DASH_URL else ""

    for j in db.q("SELECT * FROM jobs WHERE type='record_tv' AND status='queued' "
                  "AND run_at IS NOT NULL"):
        lead = j["run_at"] - now
        if 0 < lead <= TV_NOTIFY_LEAD_START and j["id"] not in _tv_notified_start:
            _tv_notified_start.add(j["id"])
            p = json.loads(j["params"] or "{}")
            tg(f"📺 <b>Скоро запись</b> — {p.get('title','?')} "
               f"({p.get('channel','?')}) в {_fmt_hm(j['run_at'])} "
               f"(через ~{int(lead//60)} мин).{link}")

    for j in db.running_jobs():
        if j["type"] != "record_tv" or j["id"] in _tv_notified_end:
            continue
        prog = json.loads(j["progress"] or "{}")
        dur, el = prog.get("duration"), prog.get("elapsed")
        if dur and el is not None and 0 <= (dur - el) <= TV_NOTIFY_LEAD_END:
            _tv_notified_end.add(j["id"])
            p = json.loads(j["params"] or "{}")
            tg(f"⏹ <b>Запись скоро завершится</b> — {p.get('title','?')} "
               f"({p.get('channel','?')}), осталось ~{int((dur-el)//60)} мин. "
               f"Проверь, не идёт ли ещё фильм (реклама могла сдвинуть конец).{link}")


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
                _tv_reminders()
                db.prune_heartbeats()
            except Exception:
                pass
            await asyncio.sleep(60)

    asyncio.create_task(loop())


app.mount("/", StaticFiles(directory=str(Path(__file__).parent / "static"), html=True))
