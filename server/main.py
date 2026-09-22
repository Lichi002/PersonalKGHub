"""主服务入口：FastAPI + 提取 worker 线程 + 采集器 TCP 接收线程。

启动：.venv/Scripts/python.exe -m uvicorn server.main:app --port 47600
同时托管 web/dist 的前端静态构建（2026-09-22 起：门户直接开 47600，
不再需要 Vite dev server；改前端代码后须 npm run build 才生效）。
"""
import json
import logging
import os
import socket
import threading
import time

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import api, config, ingest, tree
from .extract import run_batch
from .schema import connect, get_conn

log = logging.getLogger("uvicorn.error")

app = FastAPI(title="PersonalKGHub")
app.include_router(api.router)

# 前端静态托管：dist 存在才挂载（挂在 / 上，/api 路由注册在前、优先命中）。
# 前端用 hash 路由，只需 / 返回 index.html。
_WEB_DIST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "dist")
if os.path.isdir(_WEB_DIST):
    app.mount("/", StaticFiles(directory=_WEB_DIST, html=True), name="web")
else:
    log.warning("web/dist 不存在，静态页面未托管（先跑 npm run build）")


def _extract_worker():
    conn = get_conn()
    while True:
        try:
            n = run_batch(conn, limit=50)
            if n == 0:
                time.sleep(2)
        except Exception:
            log.exception("extract worker batch failed")
            time.sleep(5)


def _collector_listener():
    """接收提权采集器的 JSON lines（scan dump / USN 事件）。"""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", config.COLLECTOR_PORT))
    srv.listen(2)
    while True:
        conn_sock, addr = srv.accept()
        threading.Thread(target=_handle_collector, args=(conn_sock,),
                         daemon=True).start()


def _purge_ghosts(conn, scan_start: float):
    """scan_end 对账：删除不在本次扫描名单里、且扫描窗口前就存在的文件行
    （FRN 已换代的幽灵）；名单之外的正文/FTS 一并清理。"""
    conn.execute(
        """DELETE FROM files WHERE mtime < ? AND NOT EXISTS
             (SELECT 1 FROM scan_seen s
              WHERE s.volume=files.volume AND s.frn=files.frn)""",
        (scan_start,))
    conn.execute(
        """DELETE FROM contents WHERE file_pk NOT IN
             (SELECT volume || frn FROM files)""")
    conn.execute(
        """DELETE FROM fts WHERE rowid IN
             (SELECT rid FROM fts_map WHERE file_pk NOT IN
                (SELECT volume || frn FROM files))""")
    conn.execute(
        """DELETE FROM fts_map WHERE file_pk NOT IN
             (SELECT volume || frn FROM files)""")
    conn.execute("DELETE FROM scan_seen")
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    log.info("ghost purge done, files now %d", n)


def _handle_collector(sock):
    buf = b""
    batch = []
    seen = []
    scan_start = None
    # 采集器存活上报：前端状态 pill 靠它说真话。空行心跳也算「活着」的证据，
    # 所以在这里（收到字节就算）而不是在解析出消息之后更新。
    api.collector_state["connected"] += 1
    api.collector_state["last_seen"] = time.time()
    try:
        with sock:
            sock.settimeout(600)
            while True:
                try:
                    chunk = sock.recv(1 << 20)
                except socket.timeout:
                    break
                if not chunk:
                    break
                api.collector_state["last_seen"] = time.time()
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if msg.get("type") == "scan":
                        if scan_start is None:
                            scan_start = time.time()
                        rec = msg["rec"]
                        batch.append(rec)
                        seen.append((rec["v"], rec["frn"]))
                        if len(batch) >= 2000:
                            _apply_records(get_conn(), batch)
                            get_conn().executemany(
                                "INSERT OR IGNORE INTO scan_seen "
                                "VALUES(?,?)", seen)
                            get_conn().commit()
                            batch, seen = [], []
                    elif msg.get("type") == "event":
                        # 单条事件失败不致命：断线窗口靠重连全量重扫自愈
                        try:
                            _apply_event(get_conn(), msg)
                        except Exception:
                            log.exception("apply event failed: %s",
                                          msg.get("op"))
                    elif msg.get("type") == "scan_end":
                        _apply_records(get_conn(), batch)
                        if seen:
                            get_conn().executemany(
                                "INSERT OR IGNORE INTO scan_seen "
                                "VALUES(?,?)", seen)
                        batch, seen = [], []
                        if scan_start is not None:
                            _purge_ghosts(get_conn(), scan_start)
                        tree.rebuild(get_conn())
        if batch:
            _apply_records(get_conn(), batch)
    except Exception:
        log.exception("collector handler crashed")
    finally:
        # 断线就必须把连接数减回去，否则 /api/stats 会一直说「采集器在跑」
        api.collector_state["connected"] = max(
            0, api.collector_state["connected"] - 1)
        log.info("collector disconnected, connected=%d",
                 api.collector_state["connected"])


def _apply_records(conn, recs):
    # 目录先入（文件拼路径要查祖先链，目录在同批先到位可减少断链）
    for rec in recs:
        if rec["t"] == "d":
            # 不能 INSERT OR REPLACE：它会把 kept 冲回默认 0。扫描中途断连时，
            # 残留 batch 会走到循环外那句 _apply_records，而 scan_end 的
            # tree.rebuild 永远不会执行，kept 就永久脏掉（曾把 C:\ 根冲成 0，
            # 整棵 C 盘树从门户里消失）。新目录默认 kept=0，已存在的只更新关系。
            conn.execute(
                "INSERT INTO dirs(volume,frn,parent_frn,name) VALUES(?,?,?,?) "
                "ON CONFLICT(volume,frn) DO UPDATE SET "
                "parent_frn=excluded.parent_frn, name=excluded.name",
                (rec["v"], rec["frn"], rec["p"], rec["n"]))
    for rec in recs:
        if rec["t"] != "d":
            ingest.upsert_file(conn, rec)
    conn.commit()


def _apply_event(conn, msg):
    # collector 发的是拍平格式 {"type":"event","op":...,"v":...,"frn":...}，
    # 兼容旧的嵌套 {"rec": {...}} 写法
    rec = msg.get("rec") or msg
    if msg.get("op") == "delete":
        ingest.delete_file(conn, msg["v"], msg["frn"])
    elif rec.get("t") == "d":
        conn.execute(
            "INSERT OR REPLACE INTO dirs(volume,frn,parent_frn,name,kept) "
            "VALUES(?,?,?,?,1)",
            (rec["v"], rec["frn"], rec["p"], rec["n"]))
        conn.commit()
    else:
        ingest.upsert_file(conn, rec)
        conn.commit()


@app.on_event("startup")
def startup():
    threading.Thread(target=_extract_worker, daemon=True).start()
    threading.Thread(target=_collector_listener, daemon=True).start()
