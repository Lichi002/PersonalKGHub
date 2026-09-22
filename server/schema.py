"""SQLite 建表与连接。库文件在 D 盘，WAL 模式。

连接按线程隔离（thread-local）：FastAPI 请求线程、提取 worker、
采集器接收线程各自持有连接，避免跨线程使用；WAL + busy_timeout
处理并发写。
"""
import os
import sqlite3
import threading

from . import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS dirs(
  volume     TEXT NOT NULL,
  frn        INTEGER NOT NULL,
  parent_frn INTEGER NOT NULL,
  name       TEXT NOT NULL,
  kept       INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(volume, frn)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS files(
  volume     TEXT NOT NULL,
  frn        INTEGER NOT NULL,
  parent_frn INTEGER NOT NULL,
  name       TEXT NOT NULL,
  ext        TEXT NOT NULL,
  size       INTEGER NOT NULL DEFAULT 0,
  mtime      INTEGER NOT NULL DEFAULT 0,
  path       TEXT NOT NULL DEFAULT '',
  image_count INTEGER NOT NULL DEFAULT 0,
  scanned    INTEGER NOT NULL DEFAULT 0,
  status     TEXT NOT NULL DEFAULT 'pending',  -- pending/extracted/failed/cloud
  PRIMARY KEY(volume, frn)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);

-- 正文燃料（压缩存储，UI 不直接展示）
CREATE TABLE IF NOT EXISTS contents(
  file_pk  TEXT PRIMARY KEY,
  text_zst BLOB NOT NULL
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS tags(
  file_pk TEXT NOT NULL,
  tag     TEXT NOT NULL,
  PRIMARY KEY(file_pk, tag)
) WITHOUT ROWID;

-- 点击行为日志（推荐排序的信号源，2026-09-21 起先只记录、不参与排序）。
-- 只存原始事件、永不删、不存聚合：权重/衰减/时间窗全在读取时算，
-- 才能事后调参重算（点击数据无法回溯，聚合了就等于锁死）。
CREATE TABLE IF NOT EXISTS clicks(
  id       INTEGER PRIMARY KEY,
  -- 归一化小写路径：跨 FRN 换代的稳定身份
  -- （Excel/WPS 保存 = 删旧建新，用 pk 记会让编辑一次就丢历史）
  path_key TEXT    NOT NULL,
  file_pk  TEXT    NOT NULL,   -- 点击当时的 pk，仅供即时展示/调试
  kind     TEXT    NOT NULL,   -- open | locate | detail | tree | timeline
  q        TEXT    NOT NULL DEFAULT '',  -- 产生本次点击的查询词（「同查询点击」的前提）
  ts       INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clicks_path_ts ON clicks(path_key, ts);

-- FTS5 trigram：中文子串 + ASCII >=3 字符。
-- contentless：不存原文（省 ~1GB），摘要高亮由 api._snippet 解压 contents 生成；
-- contentless_delete 使 rowid DELETE 合法（须 SQLite >= 3.43）
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
  file_pk UNINDEXED, path_name, content, tokenize='trigram',
  content='', contentless_delete=1
);

-- file_pk 在 fts 里是 UNINDEXED（按它删除=全表扫描），用 rid 映射走 rowid 删除
CREATE TABLE IF NOT EXISTS fts_map(
  file_pk TEXT PRIMARY KEY,
  rid     INTEGER NOT NULL UNIQUE
) WITHOUT ROWID;

-- 全量重扫的"在场名单"：scan_end 时据此清掉幽灵行（FRN 已换代的旧行）
CREATE TABLE IF NOT EXISTS scan_seen(
  volume TEXT NOT NULL,
  frn    INTEGER NOT NULL,
  PRIMARY KEY(volume, frn)
) WITHOUT ROWID;
"""


def _migrate_fts_map(conn: sqlite3.Connection):
    """存量 fts 行补 fts_map（只在 fts_map 为空时扫一次）。"""
    if conn.execute("SELECT 1 FROM fts_map LIMIT 1").fetchone() is not None:
        return
    conn.execute(
        "INSERT OR IGNORE INTO fts_map(file_pk, rid) "
        "SELECT file_pk, rowid FROM fts")
    conn.commit()


def connect() -> sqlite3.Connection:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.executescript(SCHEMA)
    _migrate_fts_map(conn)
    return conn


def get_conn() -> sqlite3.Connection:
    """当前线程的连接（惰性创建）。"""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = connect()
        _local.conn = conn
    return conn
