/** 规格 §6.1：今年内 MM-dd HH:mm，跨年 yyyy-MM-dd。 */
export function fmtTime(ts) {
  if (!ts || ts <= 0) return '—'
  const d = new Date(ts * 1000)
  const p = (n) => String(n).padStart(2, '0')
  if (d.getFullYear() === new Date().getFullYear()) {
    return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
  }
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/** 规格 §6.1：<1KB 显示 B；<1MB 显示整数 KB；否则 MB（1 位小数）。 */
export function fmtSize(n) {
  if (!n || n <= 0) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1048576) return `${Math.round(n / 1024)} KB`
  return `${(n / 1048576).toFixed(1)} MB`
}

export function fmtNum(n) {
  return (n ?? 0).toLocaleString('en-US')
}

/** 顶栏状态 pill（规格 §4.3）。只说后端能证实的事，四种状态的优先级：
 *  连不上 > 采集器掉线 > 正在提取 > 正常。
 *
 *  - collector_connected 由服务端接收线程维护（采集器 30s 真发一个空行心跳），
 *    是硬事实。2026-09-21 采集器静默死了 3 小时，界面上毫无痕迹——所以这一态
 *    要比 busy 更显眼，但仍不是红色（搜索本身还好用，别让人以为服务挂了）。
 *  - 采集器掉线排在提取进度前面：那是查得出来的故障，而 pending 会自己跑完。
 *  - 判断用 === false 而不是 falsy：字段缺失是「不知道」，不是「没连上」——
 *    后端还没重启（旧代码没这个字段）时不能冤枉采集器。
 */
export function pillOf(offline, stats) {
  if (offline) return { cls: 'off', text: '索引服务未连接' }
  if (stats?.collector_connected === false) {
    return {
      cls: 'warn',
      text: '采集器未运行 · 索引已停止更新',
      title: '后端还能搜索，但采集器没连上——新文件、改名、删除都不会再进索引。'
        + '检查计划任务 PersonalKGHub-Collector 是否在跑。',
    }
  }
  const pending = stats?.by_status?.pending || 0
  if (pending > 0) return { cls: 'busy', text: `正在提取 ${fmtNum(pending)} 个文档…` }
  return { cls: 'ok', text: `已索引 ${fmtNum(stats?.files)} 个文件` }
}

/** 类型色分组（规格 §3 的 --cat-N）。演示类规格里没定义，我们自己补了 --cat-6。 */
export function catOf(ext) {
  const e = (ext || '').toLowerCase()
  if (e === '.pdf') return 'pdf'
  if (e === '.docx' || e === '.doc' || e === '.md' || e === '.txt') return 'doc'
  if (e === '.xlsx' || e === '.xls') return 'sheet'
  if (e === '.pptx' || e === '.ppt') return 'slide'
  return 'other'
}

/** 类型 chip 上的字：扩展名去点后大写，等宽 11px。 */
export function extLabel(ext) {
  return (ext || '').replace('.', '').toUpperCase() || '—'
}

/** 时间筛选 → 后端的 from_（unix 秒）。后端没有"本周"概念，前端算好边界。 */
export function timeRange(key) {
  if (!key) return {}
  const now = new Date()
  const start = new Date(now)
  start.setHours(0, 0, 0, 0)
  if (key === 'week') start.setDate(start.getDate() - 6)
  if (key === 'month') start.setMonth(start.getMonth() - 1)
  if (key === 'year') start.setFullYear(start.getFullYear() - 1)
  return { from_: Math.floor(start.getTime() / 1000) }
}

export const TIME_OPTIONS = [
  ['', '不限时间'],
  ['today', '今天'],
  ['week', '近 7 天'],
  ['month', '近 1 个月'],
  ['year', '近 1 年'],
]

export const TYPE_OPTIONS = [
  ['', '全部类型'],
  ['pdf', 'PDF'],
  ['docx', 'Word'],
  ['xlsx', 'Excel'],
  ['pptx', 'PowerPoint'],
  ['md', 'Markdown'],
  ['txt', '纯文本'],
]

/** 文件提取状态 → 中文（预览栏等处显示用）。 */
export const STATUS_LABEL = {
  pending: '待解析',
  extracted: '已解析',
  failed: '解析失败',
  cloud: '云端未下载',
}

/** catOf 的英文名 → styles.css 里的 --cat-N 变量（变量是数字命名，不是名字）。
 *  之前直接拼 var(--cat-pdf) 是未定义变量，颜色整条失效。 */
const CAT_VAR = { doc: 1, pdf: 2, sheet: 5, slide: 6, other: 5 }
export function catVar(ext) {
  return `var(--cat-${CAT_VAR[catOf(ext)] || 5})`
}
