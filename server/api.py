"""REST API。搜索：文件名/标签 分词级 Jaccard 为主，bm25 衰减加权。"""
import os
import sqlite3
import subprocess
import time
import zlib

import jieba

from fastapi import APIRouter
from pydantic import BaseModel

from . import config
from .schema import get_conn

router = APIRouter(prefix="/api")


# ---------- search ----------

_RESULT_TTL = 60  # 秒：同一查询短缓存，吸收防抖重复请求 + 高频词召回成本
_result_cache = {}


def _cache_put(key, result):
    if len(_result_cache) > 100:  # 粗略防膨胀：满了清一半
        for k in sorted(_result_cache, key=lambda k: _result_cache[k][0])[:50]:
            _result_cache.pop(k, None)
    _result_cache[key] = (time.time(), result)

@router.get("/search")
def search(q: str = "", ext: str = "", dir_: str = "",
           from_: int = 0, to: int = 0, limit: int = 50):
    ckey = (q, ext, dir_, from_, to, limit)
    hit = _result_cache.get(ckey)
    if hit and time.time() - hit[0] < _RESULT_TTL:
        return hit[1]
    conn = get_conn()
    conds, params = ["f.status='extracted'"], []
    if ext:
        conds.append("f.ext=?")
        params.append(ext.lower() if ext.startswith(".") else f".{ext.lower()}")
    if dir_:
        conds.append("f.path LIKE ?")
        params.append(dir_.rstrip("\\") + "\\%")
    if from_:
        conds.append("f.mtime >= ?")
        params.append(from_)
    if to:
        conds.append("f.mtime <= ?")
        params.append(to)

    if len(q.strip()) >= 3:
        # 排序（2026-09-21 调权：0.55/0.45 归一，sim ∈ [0,1]）：
        #   sim   = 0.55 × Jaccard(查询, 文件名词集) + 0.45 × max(Jaccard(查询, 各标签))
        #   final = sim + 0.5 × bm25n × (1 − sim)   # 衰减融合，已覆盖不再加成
        #   bm25n = FTS 召回排名百分位（bm25 只做召回+此项，不再主导排序）
        fts_sql = f"""
          SELECT m.file_pk FROM fts
            JOIN fts_map m ON m.rid = fts.rowid
            JOIN files f ON f.volume || f.frn = m.file_pk
          WHERE fts MATCH ? AND {' AND '.join(conds)}
          ORDER BY bm25(fts, 1.0, 10.0, 1.0) LIMIT 200"""
        cand_list = [r[0] for r in
                     conn.execute(fts_sql, [_quote_fts(q)] + params).fetchall()]
        n_cand = len(cand_list)
        bm25n = {pk: (n_cand - i) / n_cand
                 for i, pk in enumerate(cand_list)}
        cand_set = set(cand_list)

        idx = _sim_index(conn)
        qt = _tokens(q.strip())
        scored = []
        # 全库打分同样要过 conds（ext/dir_/时间过滤），否则筛选漏文件
        for r in conn.execute(
                f"""SELECT f.volume, f.frn, f.name, f.path, f.ext, f.size,
                           f.mtime, f.scanned, f.image_count
                    FROM files f WHERE {' AND '.join(conds)}""", params):
            pk = config.pk(r[0], r[1])
            nsim = _jaccard(qt, idx["names"].get(pk, set()))
            tset = idx["tags"].get(pk)
            tsim = _jaccard(qt, tset) if tset else 0.0
            sim = 0.55 * nsim + 0.45 * tsim
            if sim > 0 or pk in cand_set:
                final = sim + 0.5 * bm25n.get(pk, 0.0) * max(0.0, 1 - sim)
                scored.append((final, r[6], r, nsim > 0, tsim > 0))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        hits = []
        for s, _mt, r, hn, ht in scored[:limit]:
            card = _card(*r, None, 0)
            card["snippet"] = _snippet(conn, card["pk"], q.strip())
            card["score"] = round(s, 3)
            # 命中来源：让前端说清「为什么排在这里」，也是排序的调试视图
            card["hit_name"] = hn
            card["hit_tags"] = ht
            card["hit_fts"] = card["pk"] in cand_set
            hits.append(card)
        result = {"hits": hits}
        _cache_put(ckey, result)
        return result
    else:  # 短查询走 LIKE（trigram 需要 >=3 字符）
        like = f"%{q.strip()}%"
        sql = f"""
          SELECT f.volume, f.frn, f.name, f.path, f.ext, f.size, f.mtime,
                 f.scanned, f.image_count, NULL, 0
          FROM files f
          WHERE (f.name LIKE ? OR f.path LIKE ?) AND {' AND '.join(conds)}
          ORDER BY f.mtime DESC LIMIT ?"""
        rows = conn.execute(sql, [like, like] + params + [limit]).fetchall()

    q_low = q.strip().lower()
    hits = []
    for r in rows:
        card = _card(*r)  # 短查询没有 bm25，只有 LIKE 命中的位置
        name_hit = q_low in (r[2] or "").lower()
        card["hit_name"] = name_hit
        card["hit_tags"] = False
        # 命中不在文件名里 → 必然是路径；前端据此显示「路径命中」
        card["hit_fts"] = not name_hit and q_low in (r[3] or "").lower()
        hits.append(card)
    result = {"hits": hits}
    _cache_put(ckey, result)
    return result


def _quote_fts(q: str) -> str:
    return '"' + q.replace('"', '""') + '"'


# ---------- 文件名/标签相似度（2026-09-20 拍板方案） ----------
# 词级 Jaccard：jieba 搜索模式分词（长词+子词都出，避免两边粒度不一致漏配），
# 单字 token 丢弃（专有名词退化为单字是主要噪声源）。

_SIM_TTL = 300  # 名片索引缓存秒数（标签/文件有变更时最多延迟 5 分钟）


_token_memo = {}


def _tokens(s: str) -> set:
    # 记忆化：标签大量重复（同一关键词出现在几百篇文档），避免重复分词
    t = _token_memo.get(s)
    if t is None:
        t = {w for w in (w.strip() for w in jieba.lcut_for_search(s))
             if len(w) > 1}
        _token_memo[s] = t
    return t


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


_sim_cache = {"at": 0.0, "names": {}, "tags": {}}


def _sim_index(conn) -> dict:
    """pk → 文件名词集 / 标签词集（并集），惰性加载 + TTL。"""
    now = time.time()
    if now - _sim_cache["at"] > _SIM_TTL:
        names, tags = {}, {}
        for vol, frn, name in conn.execute(
                "SELECT volume, frn, name FROM files WHERE status='extracted'"):
            names[config.pk(vol, frn)] = _tokens(name)
        for pk, tag in conn.execute("SELECT file_pk, tag FROM tags"):
            tags.setdefault(pk, set()).update(_tokens(tag))
        _sim_cache.update(at=now, names=names, tags=tags)
    return _sim_cache


def _snippet(conn, pk: str, q: str) -> str | None:
    """FTS 已不存原文，摘要现场解压 contents 生成（仅对最终 N 行调用）。"""
    row = conn.execute("SELECT text_zst FROM contents WHERE file_pk=?",
                       (pk,)).fetchone()
    if not row:
        return None
    text = zlib.decompress(row[0]).decode("utf-8")
    i = text.lower().find(q.lower())
    if i < 0:
        return None  # 命中在文件名/路径，正文无该词
    start = max(0, i - 50)
    end = min(len(text), i + len(q) + 150)
    return ("…" if start else "") + text[start:i] + "[[" + \
        text[i:i + len(q)] + "]]" + text[i + len(q):end] + \
        ("…" if end < len(text) else "")


def _card(vol, frn, name, path, ext, size, mtime, scanned, images,
          snip, rank) -> dict:
    return {"pk": config.pk(vol, frn), "name": name, "path": path,
            "ext": ext, "size": size, "mtime": mtime,
            "scanned": bool(scanned), "image_count": images,
            "snippet": snip}


# ---------- tree ----------

def _dir_path(conn, vol: str, frn: int, cache: dict, depth: int = 0) -> str | None:
    """目录完整路径：沿 parent_frn 上溯逐段拼。dirs 表没有 path 列（骨架表刻意
    冗余最小），所以现场算——树是懒加载的，每层只有几十个子目录、深度十几层，
    这点 PK 查询可忽略；cache 让同一次请求里的兄弟目录共享祖先链。

    拼接规则与 ingest._compute_path / tree.dir_path 保持一致（同一份 path 才能
    被 /api/search 的 dir_ 前缀过滤命中）：base 以 \\ 结尾就不再补。
    """
    key = (vol, frn)
    if key in cache:
        return cache[key]
    if depth > 64:  # 目录成环（理论不该有）时兜底，别把请求拖死
        return None
    row = conn.execute("SELECT parent_frn, name FROM dirs WHERE volume=? AND frn=?",
                       key).fetchone()
    if not row:
        cache[key] = None
        return None
    parent_frn, name = row
    if parent_frn in (0, frn):  # 卷根：它的 name 本身就带尾部反斜杠
        path = name
    else:
        base = _dir_path(conn, vol, parent_frn, cache, depth + 1)
        if base is None:
            path = None
        else:
            path = base + name if base.endswith("\\") else base + "\\" + name
    cache[key] = path
    return path


@router.get("/tree")
def tree_node(vol: str = "", frn: int = 0):
    conn = get_conn()
    cache: dict = {}
    if not vol:  # 根：列出各卷根目录
        rows = conn.execute(
            "SELECT volume, frn, name FROM dirs WHERE parent_frn=0 AND kept=1"
        ).fetchall()
        return {"children": [
            {"volume": v, "frn": f, "name": n,
             "path": _dir_path(conn, v, f, cache),
             "label": n} for v, f, n in rows]}
    row = conn.execute(
        "SELECT name FROM dirs WHERE volume=? AND frn=?",
        (vol, frn)).fetchone()
    if not row:
        return {"children": []}
    base = row[0]
    children = conn.execute(
        """SELECT d.volume, d.frn, d.name,
                  (SELECT COUNT(*) FROM files f
                   WHERE f.volume=d.volume AND f.parent_frn=d.frn) AS nf
           FROM dirs d WHERE d.volume=? AND d.parent_frn=? AND d.kept=1
           ORDER BY d.name""", (vol, frn)).fetchall()
    # kept=1 的目录必然连着知识文件，一级一级都是 kept
    # path 是前端「只搜这个目录」用的——dirs 表没有 path 列，现场算了出来
    return {"label": base, "path": _dir_path(conn, vol, frn, cache),
            "children": [
                {"volume": v, "frn": f, "name": n, "files": nf,
                 "path": _dir_path(conn, v, f, cache),
                 "label": n} for v, f, n, nf in children]}


@router.get("/dir_files")
def dir_files(vol: str, frn: int):
    rows = get_conn().execute(
        """SELECT frn, name, ext, size, mtime, status, scanned
           FROM files WHERE volume=? AND parent_frn=? ORDER BY mtime DESC""",
        (vol, frn)).fetchall()
    return {"files": [
        {"pk": config.pk(vol, f), "name": n, "ext": e, "size": s,
         "mtime": m, "status": st, "scanned": bool(sc)}
        for f, n, e, s, m, st, sc in rows]}


# ---------- timeline ----------

@router.get("/timeline")
def timeline(month: str = "", limit: int = 200):
    conn = get_conn()
    if month:
        rows = conn.execute(
            """SELECT volume, frn, name, path, ext, mtime FROM files
               WHERE mtime > 0
                 AND strftime('%Y-%m', mtime, 'unixepoch', 'localtime')=?
               ORDER BY mtime DESC LIMIT ?""", (month, limit)).fetchall()
        return {"month": month, "files": [_mini(*r) for r in rows]}
    rows = conn.execute(
        """SELECT strftime('%Y-%m', mtime, 'unixepoch', 'localtime') AS m,
                  COUNT(*) FROM files
           WHERE mtime > 0
           GROUP BY m ORDER BY m DESC LIMIT 24""").fetchall()
    return {"months": [{"month": m, "count": c} for m, c in rows]}


def _mini(vol, frn, name, path, ext, mtime) -> dict:
    return {"pk": config.pk(vol, frn), "name": name, "path": path,
            "ext": ext, "mtime": mtime}


# ---------- doc detail & open ----------

@router.get("/doc/{pk}")
def doc_detail(pk: str):
    conn = get_conn()
    vol, frn = pk[:2], int(pk[2:])
    row = conn.execute(
        """SELECT name, path, ext, size, mtime, status, scanned, image_count
           FROM files WHERE volume=? AND frn=?""", (vol, frn)).fetchone()
    if not row:
        return {"error": "not found"}
    tags = [t for (t,) in conn.execute(
        "SELECT tag FROM tags WHERE file_pk=?", (pk,))]
    return {"pk": pk, "name": row[0], "path": row[1], "ext": row[2],
            "size": row[3], "mtime": row[4], "status": row[5],
            "scanned": bool(row[6]), "image_count": row[7], "tags": tags}


# ---------- preview ----------

PREVIEW_CHARS = 5000


@router.get("/preview/{pk}")
def preview(pk: str, q: str = ""):
    """右侧预览面板：压缩正文现场解压（文件无需在盘上也能看）。

    带 q 时返回「命中位置」：正文命中总次数 + 最多 3 条上下文（[[ ]] 标记），
    供预览栏的 hit-card 展示——比单条摘要信息量大。
    """
    row = get_conn().execute(
        "SELECT text_zst FROM contents WHERE file_pk=?", (pk,)).fetchone()
    if not row:
        return {"text": "", "truncated": False,
                "reason": "未提取或提取失败，请打开原文件查看"}
    text = zlib.decompress(row[0]).decode("utf-8")
    out = {"text": text[:PREVIEW_CHARS],
           "truncated": len(text) > PREVIEW_CHARS}
    if q.strip():
        out["match_count"], out["contexts"] = _find_contexts(text, q.strip())
    return out


def _find_contexts(text: str, q: str, max_n: int = 3):
    """正文里查询词的全部命中次数 + 前 max_n 条上下文（[[ ]] 标记）。"""
    tl, ql = text.lower(), q.lower()
    positions, start = [], 0
    while len(positions) < 500:  # 上限防极端文档卡死
        i = tl.find(ql, start)
        if i < 0:
            break
        positions.append(i)
        start = i + len(ql)
    contexts = []
    for i in positions[:max_n]:
        s = max(0, i - 50)
        e = min(len(text), i + len(q) + 150)
        contexts.append(("…" if s else "") + text[s:i] + "[[" +
                         text[i:i + len(q)] + "]]" + text[i + len(q):e] +
                         ("…" if e < len(text) else ""))
    return len(positions), contexts


class OpenReq(BaseModel):
    pk: str
    mode: str = "open"  # open | locate


@router.post("/open")
def open_file(req: OpenReq):
    row = get_conn().execute(
        "SELECT path FROM files WHERE volume=? AND frn=?",
        (req.pk[:2], int(req.pk[2:]))).fetchone()
    if not row:
        return {"ok": False, "error": "not found"}
    path = row[0]
    if req.mode == "locate":
        subprocess.Popen(["explorer", "/select,", path])
    else:
        os.startfile(path)  # noqa: S606
    return {"ok": True}


# ---------- 点击日志（推荐排序的信号源；当前只记录，不参与排序） ----------

CLICK_DEDUPE = 1800  # 秒：同一文件 30 分钟内只记一次「最强」的那个动作

# 动作权重。现在只用于去重时比较强弱；将来排序的权重也从这里取，
# 所以别把权重写进表里——改这里就能重算历史数据。
KIND_WEIGHTS = {"open": 1.0, "detail": 0.5, "locate": 0.3,
                "tree": 0.3, "timeline": 0.3}


class ClickReq(BaseModel):
    pk: str
    kind: str = "detail"
    q: str = ""


@router.post("/click")
def record_click(req: ClickReq):
    """记录一次点击。任何失败都只返回 ok=False——埋点绝不该影响正常使用。

    去重规则：同一文件 30 分钟内只留一条，且保留其中权重最高的动作
    （先点卡片看详情、再点「打开文件」→ 升级成 open，而不是记两条）。
    """
    if req.kind not in KIND_WEIGHTS:
        return {"ok": False, "error": "bad kind"}
    pk = req.pk
    try:
        vol, frn = pk[:2], int(pk[2:])
    except (ValueError, IndexError):
        return {"ok": False, "error": "bad pk"}
    conn = get_conn()
    row = conn.execute("SELECT path FROM files WHERE volume=? AND frn=?",
                       (vol, frn)).fetchone()
    if not row or not row[0]:
        return {"ok": False, "error": "not found"}
    path_key = row[0].lower()
    now = int(time.time())
    prev = conn.execute(
        "SELECT id, kind FROM clicks WHERE path_key=? AND ts>=? "
        "ORDER BY ts DESC LIMIT 1", (path_key, now - CLICK_DEDUPE)).fetchone()
    if prev is not None:
        if KIND_WEIGHTS[req.kind] > KIND_WEIGHTS[prev[1]]:
            conn.execute("UPDATE clicks SET kind=?, q=?, ts=? WHERE id=?",
                         (req.kind, req.q, now, prev[0]))
            conn.commit()
            return {"ok": True, "action": "upgraded"}
        return {"ok": True, "action": "deduped"}
    conn.execute(
        "INSERT INTO clicks(path_key, file_pk, kind, q, ts) VALUES(?,?,?,?,?)",
        (path_key, pk, req.kind, req.q, now))
    conn.commit()
    return {"ok": True, "action": "inserted"}


# ---------- stats ----------

# 采集器存活状态。由 main 的接收线程维护（main._handle_collector 置位）。
# 为什么不能只看日志：采集器只在收到事件时才写日志，没有文件变动就一片安静，
# 日志静默 ≠ 进程死亡（2026-09-21 采集器静默死了 3 小时，日志最后一行停在
# 死前那一刻，界面完全看不出来）。所以暴露这个真实信号：
#   connected  当前有几个采集器连接
#   last_seen  最近一次收到字节的时间（采集器 30s 心跳真发一个空行）
# 心跳是「真写字节」不是空操作，所以这个时间戳能反映进程是否还活着。
collector_state = {"connected": 0, "last_seen": 0.0}
COLLECTOR_STALE = 90  # 秒：超过这个时长没收到任何字节（含心跳）判为失联


def collector_live() -> bool:
    if collector_state["connected"] <= 0:
        return False
    seen = collector_state["last_seen"]
    return seen > 0 and time.time() - seen <= COLLECTOR_STALE


# ---------- 会话心跳（看门狗用，2026-09-22） ----------
# 前端每 10s 轮询 /api/stats，这里记下"最近一次页面心跳"。
# /api/session 只读不上报——看门狗自己轮询它，不能污染心跳。
_web_seen = {"t": 0.0}
_start = {"t": time.time()}


@router.get("/session")
def session_state():
    if _web_seen["t"] < _start["t"]:
        return {"web_idle": None}  # 后端启动后还没有页面心跳过
    return {"web_idle": round(time.time() - _web_seen["t"], 1)}


@router.post("/ping")
def ping():
    """页面心跳（Web Worker 发）：普通页面定时器会被浏览器按可见性节流
    （后台标签隐藏 5 分钟后降到 1/分钟，极端 1/小时），Worker 不受节流。"""
    _web_seen["t"] = time.time()
    return {"ok": True}


@router.get("/stats")
def stats():
    _web_seen["t"] = time.time()  # 页面心跳：前端每 10s 轮询一次本端点
    conn = get_conn()
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    n_files = q("SELECT COUNT(*) FROM files")
    by_status = dict(conn.execute(
        "SELECT status, COUNT(*) FROM files GROUP BY status").fetchall())
    db_bytes = os.path.getsize(config.DB_PATH) if os.path.exists(
        config.DB_PATH) else 0
    seen = collector_state["last_seen"]
    return {"files": n_files, "by_status": by_status,
            "by_ext": dict(conn.execute(
                "SELECT ext, COUNT(*) FROM files GROUP BY ext")),
            "dirs_kept": q("SELECT COUNT(*) FROM dirs WHERE kept=1"),
            "db_mb": round(db_bytes / 1e6, 1),
            "collector_connected": collector_live(),
            "collector_last_seen": int(seen) if seen else None,
            "clicks_total": q("SELECT COUNT(*) FROM clicks"),
            "clicks_30d": conn.execute(
                "SELECT COUNT(*) FROM clicks WHERE ts>=?",
                (int(time.time()) - 30 * 86400,)).fetchone()[0]}


# ---------- 正文访问（调试/后续嵌入用，不在 UI 暴露） ----------

def load_text(conn: sqlite3.Connection, file_pk: str) -> str | None:
    row = conn.execute(
        "SELECT text_zst FROM contents WHERE file_pk=?", (file_pk,)).fetchone()
    return zlib.decompress(row[0]).decode("utf-8") if row else None
