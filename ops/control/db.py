"""SQLite store for the TTS control plane.

Single-writer, WAL mode — the control plane is the only process touching it.
Job logs are NOT stored here (they'd bloat the DB); they go to DATA/logs/<id>.log
and are tailed from disk.
"""
import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT NOT NULL,               -- train_st2 | synth_st2 | recut_24k | audit
    device      TEXT NOT NULL DEFAULT 'gpu', -- gpu (exclusive) | cpu (parallel)
    params      TEXT NOT NULL DEFAULT '{}',  -- JSON
    status      TEXT NOT NULL DEFAULT 'queued',
                                             -- queued|running|done|failed|canceled
    priority    INTEGER NOT NULL DEFAULT 0,  -- higher runs first
    progress    TEXT NOT NULL DEFAULT '{}',  -- JSON: epoch, step, losses...
    error       TEXT,
    cancel      INTEGER NOT NULL DEFAULT 0,  -- agent polls this and kills the run
    created_at  REAL NOT NULL,
    started_at  REAL,
    finished_at REAL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

CREATE TABLE IF NOT EXISTS heartbeats (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    host          TEXT NOT NULL,
    ts            REAL NOT NULL,
    gpu_used_mb   INTEGER,
    gpu_free_mb   INTEGER,
    disk_free_gb  REAL,
    running_jobs  TEXT NOT NULL DEFAULT '[]', -- JSON list of job ids
    meta          TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_hb_ts ON heartbeats(ts);

CREATE TABLE IF NOT EXISTS checkpoints (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run        TEXT NOT NULL,       -- e.g. st2_crh_24k
    epoch      INTEGER,
    path       TEXT NOT NULL,       -- path ON THE BOX
    size_bytes INTEGER,
    keep       INTEGER NOT NULL DEFAULT 0,  -- protected from auto-prune
    synced     INTEGER NOT NULL DEFAULT 0,  -- copied to NAS?
    created_at REAL NOT NULL,
    UNIQUE(run, path)
);

-- A rendered probe set: one job -> N wavs, listenable in the browser.
CREATE TABLE IF NOT EXISTS samples (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     INTEGER,
    run        TEXT NOT NULL,
    epoch      INTEGER,
    probe_set  TEXT NOT NULL,       -- q_carrier | probe20 | ...
    params     TEXT NOT NULL DEFAULT '{}',  -- sampler params (steps, escale...)
    rel_dir    TEXT NOT NULL,       -- relative to DATA/samples
    n_clips    INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);

-- Per-clip listening verdicts (replaces the localStorage export dance).
CREATE TABLE IF NOT EXISTS verdicts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id  INTEGER NOT NULL,
    clip_idx   INTEGER NOT NULL,
    verdict    TEXT,                -- ok | bad
    comment    TEXT,
    created_at REAL NOT NULL,
    UNIQUE(sample_id, clip_idx)
);
"""


class DB:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def q(self, sql, args=()):
        cur = self._conn.execute(sql, args)
        rows = [dict(r) for r in cur.fetchall()]
        return rows

    def one(self, sql, args=()):
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def x(self, sql, args=()):
        cur = self._conn.execute(sql, args)
        self._conn.commit()
        return cur.lastrowid

    # ---------- jobs ----------

    def enqueue(self, type_, params, device="gpu", priority=0):
        return self.x(
            "INSERT INTO jobs(type, device, params, priority, created_at) VALUES(?,?,?,?,?)",
            (type_, device, json.dumps(params), priority, time.time()),
        )

    def claim_next(self, device, gpu_busy):
        """Hand the agent the next runnable job.

        The GPU is a single exclusive resource: never hand out a gpu job while
        one is already running. CPU jobs have no such lock, so probe renders can
        run *while* a training job holds the GPU — that's what lets you listen
        to samples without killing the run.
        """
        if device == "gpu" and gpu_busy:
            return None
        row = self.one(
            "SELECT * FROM jobs WHERE status='queued' AND device=? "
            "ORDER BY priority DESC, id ASC LIMIT 1",
            (device,),
        )
        if not row:
            return None
        self.x(
            "UPDATE jobs SET status='running', started_at=? WHERE id=? AND status='queued'",
            (time.time(), row["id"]),
        )
        # re-read: if another agent raced us, status won't be 'running' for us
        cur = self.one("SELECT * FROM jobs WHERE id=?", (row["id"],))
        return cur if cur and cur["status"] == "running" else None

    def finish(self, job_id, status, error=None):
        self.x(
            "UPDATE jobs SET status=?, error=?, finished_at=? WHERE id=?",
            (status, error, time.time(), job_id),
        )

    def set_progress(self, job_id, progress):
        self.x("UPDATE jobs SET progress=? WHERE id=?", (json.dumps(progress), job_id))

    def gpu_busy(self):
        return bool(self.one("SELECT 1 AS x FROM jobs WHERE status='running' AND device='gpu'"))

    def running_jobs(self):
        return self.q("SELECT * FROM jobs WHERE status='running' ORDER BY id")

    # ---------- heartbeat ----------

    def heartbeat(self, host, gpu_used, gpu_free, disk_free, running, meta):
        return self.x(
            "INSERT INTO heartbeats(host, ts, gpu_used_mb, gpu_free_mb, disk_free_gb, "
            "running_jobs, meta) VALUES(?,?,?,?,?,?,?)",
            (host, time.time(), gpu_used, gpu_free, disk_free,
             json.dumps(running), json.dumps(meta)),
        )

    def last_heartbeat(self, host=None):
        if host:
            return self.one("SELECT * FROM heartbeats WHERE host=? ORDER BY ts DESC LIMIT 1", (host,))
        return self.one("SELECT * FROM heartbeats ORDER BY ts DESC LIMIT 1")

    def prune_heartbeats(self, keep_seconds=7 * 24 * 3600):
        self.x("DELETE FROM heartbeats WHERE ts < ?", (time.time() - keep_seconds,))
