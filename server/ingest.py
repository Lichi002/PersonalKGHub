"""采集数据入库：全量 JSONL 导入 + 树剪枝。

M3 的 USN 增量事件将复用 upsert_file/delete_file 两个入口。
"""
import json
import os
import time

from . import config, tree


def _rejected(path: str, name: str) -> bool:
    """路径圈定 + 依赖目录黑名单（MFT 全枚举时的入库闸门）。"""
    if not config.in_scope(path):
        return True
    segs = path.lower().split("\\")
    if any(s in config.SKIP_DIR_NAMES for s in segs):
        return True
    if os.path.splitext(name)[1].lower() in (".md", ".txt") and \
            any(s in config.SKIP_MD_TXT_UNDER for s in segs):
        return True
    return False


def load_scan(conn, jsonl_path: str) -> dict:
    t0 = time.time()
    n_dirs = n_files = 0
    batch_dirs, batch_files = [], []

    def flush():
        nonlocal n_dirs, n_files
        if batch_dirs:
            # 同 main._apply_records：不能 OR REPLACE，会把 kept 冲回 0
            conn.executemany(
                "INSERT INTO dirs(volume,frn,parent_frn,name) VALUES(?,?,?,?) "
                "ON CONFLICT(volume,frn) DO UPDATE SET "
                "parent_frn=excluded.parent_frn, name=excluded.name",
                batch_dirs)
            batch_dirs.clear()
        if batch_files:
            conn.executemany(
                "INSERT OR REPLACE INTO files(volume,frn,parent_frn,name,ext,"
                "size,mtime) VALUES(?,?,?,?,?,?,?)", batch_files)
            batch_files.clear()

    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["t"] == "d":
                n_dirs += 1
                batch_dirs.append((r["v"], r["frn"], r["p"], r["n"]))
            else:
                n_files += 1
                batch_files.append((r["v"], r["frn"], r["p"], r["n"],
                                    _ext(r["n"]), r.get("s", 0),
                                    r.get("m", 0)))
            if len(batch_dirs) + len(batch_files) >= 10000:
                flush()
    flush()
    stats = tree.rebuild(conn)
    stats["ingest_dirs"] = n_dirs
    stats["ingest_files"] = n_files
    stats["seconds"] = round(time.time() - t0, 1)
    return stats


def upsert_file(conn, rec: dict):
    """USN 增量：单个文件 upsert，并即时拼路径。

    MFT/USN 记录没有文件大小、部分记录 mtime=0（FILETIME 0 = 1601 年），
    这里用 os.stat 补全（仅元数据，不会触发 OneDrive 占位文件下载）。
    mtime/size 都没变的文件（重连全量重扫的常态）保留原 status，
    避免每次重扫把几千个已提取文档重新提取一遍。
    """
    vol, frn, pfrn, name = rec["v"], rec["frn"], rec["p"], rec["n"]
    path = _compute_path(conn, vol, pfrn, name)
    if _rejected(path, name):
        return
    size, mtime = rec.get("s", 0), rec.get("m", 0)
    old = conn.execute(
        "SELECT size, mtime, status FROM files WHERE volume=? AND frn=?",
        (vol, frn)).fetchone()
    if (size == 0 or mtime <= 0) and path:
        try:
            st = os.stat(path)
            if size == 0:
                size = st.st_size
            if mtime <= 0:
                mtime = int(st.st_mtime)
        except OSError:
            pass
    status = "pending"
    if old is not None:
        # 旧值是 0（未知）时不判为"已变化"，让补全过程不触发重提取
        unchanged = ((old[0] == 0 or old[0] == size) and
                     (old[1] <= 0 or old[1] == mtime))
        status = old[2] if unchanged else "pending"
    conn.execute(
        "INSERT OR REPLACE INTO files(volume,frn,parent_frn,name,ext,size,"
        "mtime,path,status) VALUES(?,?,?,?,?,?,?,?,?)",
        (vol, frn, pfrn, name, _ext(name), size, mtime, path, status))
    conn.commit()


def _compute_path(conn, vol: str, pfrn: int, name: str) -> str:
    """沿 dirs 祖先链拼完整路径（增量事件时用）。"""
    parts = []
    cur = pfrn
    for _ in range(64):  # 防环
        row = conn.execute(
            "SELECT parent_frn, name FROM dirs WHERE volume=? AND frn=?",
            (vol, cur)).fetchone()
        if row is None:
            break
        parts.append(row[1])
        if row[0] == 0:
            break
        cur = row[0]
    if not parts:
        return name
    parts.reverse()
    path = parts[0]  # 根目录名以 \ 结尾（如 'C:\'）
    for part in (*parts[1:], name):
        path = path + part if path.endswith("\\") else path + "\\" + part
    return path


def fts_delete(conn, file_pk: str):
    """按 file_pk 删 FTS 行：走 fts_map 的 rowid（O(1)）。

    无映射 = 该文件从未入过 FTS（或旧迁移遗漏），直接跳过；
    千万不能退回 `DELETE FROM fts WHERE file_pk=?`——file_pk 是
    UNINDEXED，全表扫描 2GB trigram 索引会把 handler 卡死几分钟。
    """
    row = conn.execute("SELECT rid FROM fts_map WHERE file_pk=?",
                       (file_pk,)).fetchone()
    if row is not None:
        conn.execute("DELETE FROM fts WHERE rowid=?", (row[0],))
        conn.execute("DELETE FROM fts_map WHERE file_pk=?", (file_pk,))


def fts_insert(conn, file_pk: str, path_name: str, content: str):
    """插入 FTS 行并记录 rowid 映射。"""
    cur = conn.execute(
        "INSERT INTO fts(file_pk, path_name, content) VALUES(?,?,?)",
        (file_pk, path_name, content))
    conn.execute("INSERT OR REPLACE INTO fts_map(file_pk, rid) VALUES(?,?)",
                 (file_pk, cur.lastrowid))


def delete_file(conn, volume: str, frn: int):
    """USN 增量：删除文件及其正文/FTS（M3 使用）。"""
    from . import config
    file_pk = config.pk(volume, frn)
    conn.execute("DELETE FROM files WHERE volume=? AND frn=?", (volume, frn))
    conn.execute("DELETE FROM contents WHERE file_pk=?", (file_pk,))
    fts_delete(conn, file_pk)
    conn.commit()


def _ext(name: str) -> str:
    i = name.rfind(".")
    return name[i:].lower() if i >= 0 else ""
