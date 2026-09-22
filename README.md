# PersonalKGHub · 个人知识门户

一个运行在本机（Windows）的个人知识搜索门户：通过 NTFS 的 **MFT 全量枚举 + USN Journal 增量监听**采集本机知识型文件（pdf/docx/xlsx/pptx/md/txt）的元数据与正文，存入 SQLite（FTS5 trigram 全文索引），提供：

- **实时增量索引**：文件创建/修改/删除，秒级进索引；定时全量重扫 + 在场名单对账，防幽灵行
- **混合检索**：文件名/自动标签 词级 Jaccard 相似度主导排序，bm25 衰减融合兜底；每条结果标出命中来源（文件名/标签/正文/路径）
- **自动标签**：jieba 分词 + 本地语料 IDF（用你自己的文档统计，越用越贴合），每篇 top8
- **正文预览**：提取正文 zlib 压缩存储，右侧面板现场解压预览——文件被移动甚至不在盘上也能看
- **会话式运行**：桌面快捷方式一键起全部服务并打开门户；页面关闭约 2 分钟后服务自动全部停止，不留后台进程

> 平台限制：**仅 Windows**（依赖 NTFS 的 USN Journal 与 Win32 API）；采集器需管理员权限；WSL2/docker 虚拟磁盘内的文件不可见。

## 架构

```
采集器（计划任务，提权）──JSON lines──▶ 后端 FastAPI :47600 ◀──/api── 浏览器（静态托管）
   MFT 全量 + USN 增量                    SQLite WAL                  （后端吐 web/dist）
```

| 进程 | 职责 |
|------|------|
| 采集器 `collector/` | MFT 全量枚举 + USN 增量监听，推送给后端 |
| 后端 `server/` | FastAPI：检索/标签/预览 API、提取 worker、采集器 TCP 接收（47610）、静态前端托管 |
| 前端 `web/` | Vite + React，构建产物由后端托管（无独立进程） |

## 快速开始

前提：Windows 10/11，NTFS 磁盘，Python 3.12+，Node 18+（仅构建前端时需要）。

```powershell
# 1) 后端依赖
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# 2) 前端构建
cd web && npm install && npm run build && cd ..

# 3) 配置采集范围（编辑 server/config.py）
#    SCOPE_ROOTS：要索引哪些目录；SCOPE_EXCLUDES：圈内排除哪些目录
#    数据目录：默认 <系统盘>\PersonalKGHub\data 或 ~/KGHub/data，可用环境变量 KGHUB_DATA 覆盖

# 4) 注册采集器计划任务（弹一次 UAC）
powershell -ExecutionPolicy Bypass -File collector\install_task.ps1

# 5) 启动
.venv\Scripts\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 47600
# 打开 http://127.0.0.1:47600
```

可选：把 `scripts/session_start.vbs` 发送到桌面快捷方式——一键起全部服务并打开门户，页面关闭约 2 分钟后服务自动停止（`scripts/session_watchdog.py`）。

## 配置速查（server/config.py）

| 配置 | 说明 |
|------|------|
| `SCOPE_ROOTS` | 采集哪些目录（路径前缀匹配） |
| `SCOPE_EXCLUDES` | 圈内排除前缀（应用缓存等噪声目录） |
| `DOC_EXTS` | 知识文件扩展名白名单 |
| `DATA_DIR` | 数据目录（默认逻辑见文件内注释，可用环境变量 `KGHUB_DATA` 覆盖） |
| `COLLECTOR_PORT` | 采集器→后端的 TCP 端口 |

## 开发

```powershell
cd web && npm test        # 前端回归（49 断言）
cd web && npm run dev     # 前端热更新调试（5173 代理到 47600）
```

- 一次性维护脚本在 `server/tools/`（范围迁移、FTS 重建、去重、标签回填）
- 设计细节与踩坑清单：[`docs/技术方案.md`](docs/技术方案.md)
- 版本管理：见 CLAUDE.md「版本管理」节

## License

[MIT](LICENSE)
