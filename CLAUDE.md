# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目

PersonalKGHub — 运行在本机（Windows 11）的个人知识门户：NTFS MFT 全量枚举 + USN Journal 增量监听，采集知识型文件（pdf/docx/xlsx/pptx/md/txt）的元数据与正文 → SQLite（FTS5 trigram）+ jieba 标签 → FastAPI + React 门户（搜索 / 目录树 / 时间线 / 正文预览）。单机单用户，数据全部落 D 盘。

> **权威方案文档 = [`docs/技术方案.md`](docs/技术方案.md)（随代码更新）——动手前先读它。**
> 本文件只保留每次会话都必须知道的约束与约定，不重复方案细节。

## 已定案，不要再提

- **语义向量检索已取消**（2026-09-21 用户决策）。不要建议 fastembed / sqlite-vec / RRF / 嵌入模型 / 相似文档推荐。检索用「排序方案 v2」：文件名与标签的 jieba 词集 Jaccard 为主导信号，bm25 只做 FTS 召回与衰减项（见 技术方案.md §6）。
- 只收**知识型文件**；照片、代码文件（py/js/ts）、微信数据、系统文件一律不收。
- 采集范围 = `SCOPE_ROOTS` 圈定（C 盘只收 `Desktop` / `Documents` / `Downloads` / `xwechat_files`，D 盘全盘），**不是**全盘自动发现。圈定是漏杀风险最低的一层。
- 正文提取后 zlib 压缩存 `contents`（截断 100 万字符），UI **可以**预览正文（`/api/preview/{pk}`，前 5000 字）——旧的"UI 不展示正文"决策已推翻。
- 不做 OCR（MVP 只打 `scanned` 标记）、不做多模态图片描述。

## 机器环境硬约束（实测，勿凭假设）

- ThinkPad 21J70009CD：i5-13500H / 32GB / **仅 Intel Iris Xe 核显，无 NVIDIA**——一切方案按 CPU 考虑。
- C: 仅剩约 24GB，索引库/模型/大文件一律放 D:。
- **开发 shell 非管理员**：MFT/USN 卷句柄必须提权，故采集器是独立提权进程（计划任务 `PersonalKGHub-Collector`），经 TCP `47610` 把 JSON lines 喂给后端。
  实测：**运行中的后端进程在非管理员 shell 里杀不掉**（`Stop-Process` / `taskkill /F` 均报"拒绝访问"）。
  **改完 `server/` 或 `collector/` 代码 ≠ 生效**——必须重启对应进程。非管理员会话一律用自提权脚本（会弹 UAC，请用户点"是"）：
  `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\restart_backend.ps1` / `scripts\restart_collector.ps1`。
  铁律：改完代码不重启 = 用户看到的仍是旧行为；曾因此"修好的 bug"带病运行数小时。
- OneDrive 占位文件带 `FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS`，**只 stat 不 read**，避免误触发下载。
- WSL2 / docker-desktop 的文件在 VHDX 内，MFT 只能看到 vhdx 本身。
- 环境：Python 3.12.5（`.venv`，基于 miniconda3 基座）、Node 22。pip 用阿里云镜像，npm 用 npmmirror。

## 运行与调试

| 部分 | 启动方式 | 日志 |
|------|----------|------|
| 采集器 | 计划任务 `PersonalKGHub-Collector`（登录自启，提权） | `D:\PersonalKGHub\collector_log.txt` |
| 后端 | `.venv/Scripts/python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 47600` | `D:\PersonalKGHub\server_out.log` / `server_err.log` |
| 前端 | `cd web && npm run dev`（5173，`/api` 代理 → 47600） | `D:\PersonalKGHub\web_out.log` |

- 后端**不带 `--reload`**，改了 `server/` 下的代码必须重启才生效（用 `scripts/restart_backend.ps1`）。
- **前端 2026-09-22 起为静态托管**：后端直接吐 `web/dist`，门户地址 = `http://127.0.0.1:47600`，**没有 Vite/node 进程**。改 `web/src/` 后必须 `cd web && npm run build` 再刷新（构建 ~2s）；调试样式可用 `npm run dev`（5173 代理）临时起 dev server，用完停掉。
- 采集器疑似停摆（日志 `collector_log.txt` 不再增长 / 建测试文件数秒不入库）→ `scripts/restart_collector.ps1`。
- 卡死/变慢先上 `py-spy dump --pid <pid>`（`.venv` 已装）——比猜快得多。
- 库：`D:\PersonalKGHub\data\kghub.db`（约 940MB，WAL）。一次性脚本在 `server/tools/`。

## 本机踩坑（写给自己，省得重踩）

- Git Bash 里给 `powershell -Command` 传含 `$_` 的内联脚本会被转义破坏——复杂脚本一律写成 `.ps1` 文件再执行。
- robocopy 统计文件数必须有目标目录参数（用不存在的 `X:\__nosuchdest__` + `/L`）；其汇总输出为中文（"文件:"/"目录:" 行）。
- FTS 表 `file_pk` 是 UNINDEXED：`DELETE FROM fts WHERE file_pk=?` 会全表扫描 2GB trigram 索引把 handler 卡死，删除必须走 `fts_map` 的 rowid。`WHERE volume||frn=?` 无索引，要用复合主键。
- 全量重扫只 upsert、不清幽灵行，靠 `scan_seen` 对账兜底（`main.py` `_purge_ghosts`）。

## 版本管理

- GitHub 私有仓库 `Lichi002/PersonalKGHub`，初始提交 2026-09-22（54 文件）
- **仓库级代理**：`http.proxy = http://127.0.0.1:17897`（Clash 端口），push/pull 需 Clash 运行中
- 提交前过一遍 `.gitignore`：.venv / node_modules / dist / .claude / .survey / 【参考】v1.1 样式模板（内含本机真实文件名）均已排除，新增敏感文件先补 .gitignore
