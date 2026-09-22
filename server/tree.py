"""目录树：剪枝（kept 标记）+ 文件路径拼接。

kept 规则：目录子树内（含自身）至少有一个知识文档 → kept=1；
name 命中 FORCE_KEEP_DIR_NAMES 的目录强制保留。
路径规则：p=0 的根目录 name 即完整路径；其余为 parent_path + "\\" + name。
"""
import os

from . import config


def rebuild(conn) -> dict:
    """全量重算 kept 与 files.path，返回统计信息。"""
    dirs = {}   # (vol, frn) -> [parent_frn, name, kept]
    children = {}  # (vol, parent_frn) -> [frn, ...]
    for vol, frn, p, name in conn.execute(
            "SELECT volume, frn, parent_frn, name FROM dirs"):
        key = (vol, frn)
        dirs[key] = [p, name, 0]
        children.setdefault((vol, p), []).append(frn)

    # 每个目录直接拥有的知识文件数
    doc_count = {}
    for vol, p in conn.execute("SELECT volume, parent_frn FROM files"):
        doc_count[(vol, p)] = doc_count.get((vol, p), 0) + 1

    # 迭代式后序遍历（防深度递归）
    roots = [k for k in dirs if dirs[k][0] == 0]
    visited = set()
    stack = [(k, False) for k in roots]
    while stack:
        key, expanded = stack.pop()
        if key in visited:
            continue
        if not expanded:
            stack.append((key, True))
            for frn in children.get(key, ()):
                ck = (key[0], frn)
                if ck in dirs and ck not in visited:
                    stack.append((ck, False))
        else:
            visited.add(key)
            p, name, _ = dirs[key]
            force = name.lower() in config.FORCE_KEEP_DIR_NAMES
            kept = force or doc_count.get(key, 0) > 0 or any(
                (key[0], frn) in dirs and dirs[(key[0], frn)][2]
                for frn in children.get(key, ()))
            dirs[key][2] = 1 if kept else 0

    # 写回 kept（分块提交，避免长事务占写锁饿死提取 worker）
    conn.execute("UPDATE dirs SET kept=0")
    kept_rows = [(k[0], k[1]) for k, v in dirs.items() if v[2]]
    for i in range(0, len(kept_rows), 10000):
        conn.executemany(
            "UPDATE dirs SET kept=1 WHERE volume=? AND frn=?",
            kept_rows[i:i + 10000])
        conn.commit()

    # 拼文件路径：祖先链必须全 kept（知识文件的祖先天然 kept）
    def dir_path(vol, frn):
        parts = []
        key = (vol, frn)
        while key in dirs and dirs[key][0] != 0:
            parts.append(dirs[key][1])
            key = (vol, dirs[key][0])
        if key in dirs:  # p=0 的根，name 是完整路径
            parts.append(dirs[key][1])
        parts.reverse()
        path = parts[0]  # 根名以 \ 结尾（如 'D:\'），逐段拼接避免双反斜杠
        for part in parts[1:]:
            path = path + part if path.endswith("\\") else path + "\\" + part
        return path

    def join(base, name):
        # 根目录名以 \ 结尾（如 'D:\'），直接拼避免出现 'D:\\x' 双反斜杠
        if base.endswith("\\"):
            return base + name
        return f"{base}\\{name}" if base else name

    updates = []
    for vol, frn, p, name in conn.execute(
            "SELECT volume, frn, parent_frn, name FROM files"):
        base = dir_path(vol, p)
        path = join(base, name)
        updates.append((path, vol, frn))
    for i in range(0, len(updates), 10000):
        conn.executemany("UPDATE files SET path=? WHERE volume=? AND frn=?",
                         updates[i:i + 10000])
        conn.commit()

    kept_dirs = sum(1 for v in dirs.values() if v[2])
    return {"dirs_total": len(dirs), "dirs_kept": kept_dirs,
            "files": len(updates)}
