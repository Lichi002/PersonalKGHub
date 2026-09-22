r"""全局配置：路径、扩展名白名单、强制保留目录。

数据目录解析顺序（2026-09-22 参数化）：
  1. 环境变量 KGHUB_DATA
  2. 本机既有 D:\PersonalKGHub\data（历史选择，存在则沿用）
  3. 用户目录 ~/KGHub/data（新机器默认，自动创建）
"""
import os


def _resolve_data_dir() -> str:
    env = os.environ.get("KGHUB_DATA")
    if env:
        return env
    legacy = r"D:\PersonalKGHub\data"
    if os.path.isdir(legacy):
        return legacy
    return os.path.join(os.path.expanduser("~"), "KGHub", "data")


DATA_DIR = _resolve_data_dir()
DB_PATH = os.path.join(DATA_DIR, "kghub.db")

# 采集器 → 主服务
COLLECTOR_PORT = 47610

# 知识型文档扩展名白名单（小写，含点）
DOC_EXTS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    ".md", ".txt",
}

# 即使子树无知识文档也强制保留的目录（按 name 匹配，不区分大小写）
FORCE_KEEP_DIR_NAMES = {"downloads", "desktop"}

# 依赖/版本库目录：整体不进入（其中的 md 文档不是用户知识）
SKIP_DIR_NAMES = {"node_modules", ".git", ".venv", "venv", "__pycache__",
                  "site-packages", "dist-packages", ".cache", ".npm",
                  ".pnpm-store", ".gradle", ".m2"}

# 这些路径组件下的 md/txt 视为应用文档而非用户知识（office/pdf 仍收）
SKIP_MD_TXT_UNDER = {"appdata", "miniconda3", "conda_apps"}

# Office 临时文件前缀（~$xxx.docx）
OFFICE_TEMP_PREFIX = "~$"

# 开发期爬取根（M1 遗留；M3 起改用 MFT 全盘枚举，此配置仅 dev_crawler.py 使用）
DEV_CRAWL_ROOTS = [os.path.expanduser("~"), "D:\\"]

# OneDrive 云占位属性
FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS = 0x00400000
FILE_ATTRIBUTE_OFFLINE = 0x00001000


def pk(volume: str, frn: int) -> str:
    """卷内 FRN 组合成全局主键，如 'C:12345'。"""
    return f"{volume}{frn}"


# ---------- 采集范围圈定（2026-09-20 拍板：路径为主、扩展名为辅） ----------
# C 盘只收三大常用目录 + 微信 4.x 数据区（3.x 微信/企微/腾讯会议的文件区
# 都在 Documents 下自动覆盖；QQ 未装，装了再加）；D 盘工作盘全收。
# 匹配不区分大小写，前缀按目录边界对齐（路径先归一成小写带尾 \）。

_USER = os.path.expanduser("~").rstrip("\\")


def _norm(p: str) -> str:
    return p.lower().rstrip("\\") + "\\"


SCOPE_ROOTS = [
    _norm(os.path.join(_USER, "Desktop")),
    _norm(os.path.join(_USER, "Documents")),
    _norm(os.path.join(_USER, "Downloads")),
    _norm(os.path.join(_USER, "xwechat_files")),
    _norm("D:\\"),
]


def in_scope(path: str) -> bool:
    """完整路径是否在采集圈内。"""
    if not path:
        return False
    p = path.lower()
    if not any(p.startswith(r) for r in SCOPE_ROOTS):
        return False
    # 圈内排除：应用内部缓存/数据目录（位于 Documents 等圈内，但纯噪声）。
    # 注意不能按 'cache' 目录名一刀切——WXWork\<id>\Cache\File 是企微收文件的正规存放处
    p_excl = p.rstrip("\\") + "\\"
    return not any(p_excl.startswith(x) for x in SCOPE_EXCLUDES)


# 排除前缀（小写、\ 结尾）。发现新的应用噪声目录就往这里加。
SCOPE_EXCLUDES = [
    _norm(os.path.join(_USER, r"Documents\WXWork\qtCef")),
    _norm(os.path.join(_USER, r"Documents\WXWork\Subresource Filter")),
]
