"""开发期采集器：os.scandir 爬取（非提权），输出与 MFT 采集器相同的 JSONL 协议。

记录格式（每行一个 JSON）：
  目录: {"v":"C:","t":"d","frn":123,"p":456,"n":"Downloads"}
  根目录（p=0）: {"v":"C:","t":"d","frn":123,"p":0,"n":"C:\\Users\\demo"}
  文件: {"v":"C:","t":"f","frn":123,"p":456,"n":"a.pdf","s":1234,"m":1690000000}

M3 的 mft_scan.py 将产出完全相同的记录流，ingest 无感知切换。
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from server.config import (  # noqa: E402
    DOC_EXTS, OFFICE_TEMP_PREFIX, SKIP_DIR_NAMES, SKIP_MD_TXT_UNDER,
)

REPARSE_POINT = 0x00000400  # 跳过 junction/符号链接，防环
FRN_MASK = 0xFFFFFFFFFFFFFFFF


def _frn(entry, st) -> int | None:
    """scandir 缓存 stat 不含文件索引（st_ino=0），需要时回退完整 stat。"""
    if st.st_ino:
        return st.st_ino & FRN_MASK
    try:
        ino = os.stat(entry.path, follow_symlinks=False).st_ino
        return ino & FRN_MASK if ino else None
    except OSError:
        return None


def crawl(root: str, out):
    volume = os.path.splitdrive(root)[0].upper()  # "C:"
    root = os.path.abspath(root)

    st = os.stat(root)
    root_frn = st.st_ino & FRN_MASK
    # 根记录 p=0，name 存完整路径，ingest 据此拼 path
    out.write(json.dumps({"v": volume, "t": "d", "frn": root_frn, "p": 0,
                          "n": root}, ensure_ascii=False) + "\n")

    n_dirs = n_files = n_skipped = 0
    stack = [(root, root_frn)]
    while stack:
        cur, parent = stack.pop()
        cur_parts = {p.lower() for p in cur.split(os.sep)}
        try:
            it = os.scandir(cur)
        except OSError:
            n_skipped += 1
            continue
        with it:
            for entry in it:
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    n_skipped += 1
                    continue
                attrs = st.st_file_attributes
                if attrs & REPARSE_POINT:
                    n_skipped += 1
                    continue
                if entry.is_dir(follow_symlinks=False):
                    frn = _frn(entry, st)
                    if frn is None:
                        n_skipped += 1
                        continue
                    if entry.name.lower() in SKIP_DIR_NAMES:
                        n_skipped += 1
                        continue
                    n_dirs += 1
                    out.write(json.dumps(
                        {"v": volume, "t": "d", "frn": frn, "p": parent,
                         "n": entry.name}, ensure_ascii=False) + "\n")
                    stack.append((entry.path, frn))
                else:
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext not in DOC_EXTS:
                        continue
                    if entry.name.startswith(OFFICE_TEMP_PREFIX):
                        n_skipped += 1
                        continue
                    if ext in (".md", ".txt") and cur_parts & SKIP_MD_TXT_UNDER:
                        continue
                    frn = _frn(entry, st)
                    if frn is None:
                        n_skipped += 1
                        continue
                    n_files += 1
                    out.write(json.dumps(
                        {"v": volume, "t": "f", "frn": frn, "p": parent,
                         "n": entry.name, "s": st.st_size,
                         "m": int(st.st_mtime)}, ensure_ascii=False) + "\n")
        if (n_dirs + n_files) % 50000 < 100:
            print(f"  ... {volume} dirs={n_dirs} files={n_files}", flush=True)
    return volume, n_dirs, n_files, n_skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", nargs="+", default=None)
    ap.add_argument("--out", default=os.path.join(r"D:\PersonalKGHub\data",
                                                  "scan.jsonl"))
    args = ap.parse_args()
    roots = args.roots
    if roots is None:
        from server.config import DEV_CRAWL_ROOTS as roots

    t0 = time.time()
    total = [0, 0, 0]
    with open(args.out, "w", encoding="utf-8") as out:
        for root in roots:
            print(f"crawling {root} ...", flush=True)
            _, d, f, s = crawl(root, out)
            print(f"  {root}: dirs={d} files={f} skipped={s}", flush=True)
            total[0] += d
            total[1] += f
            total[2] += s
    print(f"done in {time.time()-t0:.1f}s: dirs={total[0]} files={total[1]} "
          f"skipped={total[2]} -> {args.out}")


if __name__ == "__main__":
    main()
