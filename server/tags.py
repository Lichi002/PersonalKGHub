"""标签提取（2026-09-21 方案）：本地语料 IDF + 词性过滤 + 噪声规则。

提取 worker 与 tools/backfill_tags.py 共用本模块。IDF 文件由
tools/build_idf.py 从本机语料生成（D:\\PersonalKGHub\\data\\idf.txt），
不存在时退回 jieba 内置通用词典。
"""
import os
import re

import jieba
import jieba.analyse

from . import config

IDF_PATH = os.path.join(config.DATA_DIR, "idf.txt")
TOP_K = 8
MAX_CHARS = 50_000

# 词性白名单：名词类 + 英文（jieba posseg 词集）
ALLOW_POS = ("n", "nr", "ns", "nt", "nz", "eng")

# 通用基础词：IDF 压不住的常见废话（保守清单，宁少勿滥）
_STOPWORDS_CN = {
    "工作", "信息", "基本", "要求", "相关", "内容", "文件", "使用",
    "进行", "部分", "情况", "问题", "通过", "可以", "以下", "以上",
    "包括", "完成", "需要", "说明", "介绍", "分析", "报告", "项目",
    "公司", "中国", "北京", "上海", "深圳",
}
_STOPWORDS_EN = {
    "id", "name", "type", "time", "date", "label", "status", "step",
    "test", "data", "value", "total", "page", "sheet", "null", "none",
    "true", "false", "com", "www", "http", "https", "xxx", "cust",
    "prod", "rpt", "keys", "val", "key", "row", "col",
}

_SYM_RE = re.compile(r"^[#\-—–=_*·•.。,，;；:：/\\|()\[\]{}（）<>《》\"'`~！!？?@%^&+\s]+$")
_HASHY_RE = re.compile(r"[A-Za-z]*\d[A-Za-z\d]*")


def is_noise(t: str) -> bool:
    """单条候选词的噪声判定（建 IDF 与抽标签两侧共用）。"""
    t = t.strip()
    if len(t) < 2:
        return True                       # 单字/单字母
    if _SYM_RE.match(t):
        return True                       # 纯符号（###、--- 等）
    if t.isdigit():
        return True                       # 纯数字
    if len(t) > 12 and _HASHY_RE.fullmatch(t) and \
            any(c.isupper() for c in t) and any(c.islower() for c in t):
        return True                       # 长英数混杂串（哈希/对象ID）
    if t.isascii() and t.islower() and len(t) <= 3:
        return True                       # 纯小写短英文（列名缩写 dt/nm/pk…）
    if t in _STOPWORDS_CN or t.lower() in _STOPWORDS_EN:
        return True
    return False


_idf_ready = False


def _ensure_idf():
    global _idf_ready
    if not _idf_ready:
        if os.path.exists(IDF_PATH):
            jieba.analyse.set_idf_path(IDF_PATH)
        _idf_ready = True


def extract_tags(text: str, top_k: int = TOP_K) -> list:
    """正文 → top_k 个标签。噪声词超采 3 倍后过滤，保最终数量。"""
    _ensure_idf()
    text = text[:MAX_CHARS]
    if not text.strip():
        return []
    try:
        words = jieba.analyse.extract_tags(
            text, topK=top_k * 3, allowPOS=ALLOW_POS)
    except Exception:
        return []
    out = []
    for w in words:
        if not is_noise(w):
            out.append(w)
            if len(out) >= top_k:
                break
    return out
