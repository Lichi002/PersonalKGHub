import React, { useCallback, useEffect, useRef, useState } from 'react'
import { apiGet, apiPost, recordClick } from './api.js'
import { catOf, catVar, fmtNum, pillOf, timeRange, TIME_OPTIONS, TYPE_OPTIONS } from './format.js'
import { useDebounced, useHotkeys, useMediaQuery } from './hooks.js'
import TopBar from './components/TopBar.jsx'
import SidePane from './components/SidePane.jsx'
import ResultList from './components/ResultList.jsx'
import PreviewPane from './components/PreviewPane.jsx'
import TreeView from './components/TreeView.jsx'
import TimelineView from './components/TimelineView.jsx'
import HomeView from './components/HomeView.jsx'

/** 断点：<1200px 预览栏改浮层，<860px 侧栏改抽屉。
 *  860px 那条纯靠 CSS（.side 的 transform），这里只管 1200px 这条——
 *  因为它决定了预览栏是"常驻列"还是"点了才出现的浮层"，是渲染逻辑而不只是样式。 */
const NARROW_QUERY = '(max-width: 1199px)'
const DRAWER_QUERY = '(max-width: 859px)'
const RESULT_CAP = 50 // 后端 /api/search 的默认 limit

/* URL 化状态（规格 §7）：刷新不丢查询、结果能存书签、后退能回上一个查询。
   用 hash 而不是 path——纯前端，不用给后端配路由。
   存的是「导航身份」＝模式 + 查询 + 三个筛选，不含详情选中项：
   右栏只在用户点了具体结果后才出现（2026-09-21 改版要求），不进 URL。 */
const HASH_KEYS = ['mode', 'q', 'ext', 'time', 'dir']

export function parseHash() {
  const p = new URLSearchParams(window.location.hash.replace(/^#\/?/, ''))
  const out = {}
  for (const k of HASH_KEYS) out[k] = p.get(k) || ''
  // 旧书签的 timeline → time（时间线挪进侧栏后改了 key）
  if (out.mode === 'timeline') out.mode = 'time'
  // 不带 mode 但带了查询/筛选的旧链接：用户要的是搜索，不是首页
  if (!out.mode && (out.q || out.ext || out.time || out.dir)) out.mode = 'search'
  return out
}

export function buildHash(s) {
  const p = new URLSearchParams()
  for (const k of HASH_KEYS) if (s[k]) p.set(k, s[k])
  const qs = p.toString()
  return qs ? `#/${qs}` : '#/'
}

/** 类型筛选统一成不带点的形式（TYPE_OPTIONS 的键就是 docx）。
 *  后端两种写法都认，但筛选高亮是 `ext === key` 精确比对——
 *  手写/改过的 URL 里带点就匹配不上，所以在 URL 边界归一。 */
const normExt = (e) => (e || '').replace(/^\./, '').toLowerCase()

/* localStorage 安全封装：UI 测试在 Node 里 SSR 渲染，没有 localStorage，
   直接摸会 ReferenceError。 */
const lsGet = (k) => { try { return localStorage.getItem(k) } catch { return null } }
const lsSet = (k, v) => { try { localStorage.setItem(k, v) } catch {} }

export default function App() {
  const [init] = useState(parseHash) // 只在首屏读一次 URL
  const [mode, setMode] = useState(init.mode || 'home') // home | search | tree | time
  const [q, setQ] = useState(init.q)
  const [ext, setExt] = useState(normExt(init.ext))
  const [time, setTime] = useState(init.time)
  const [dir, setDir] = useState(init.dir) // 目录前缀（来自目录树的「只搜这里」）

  const [hits, setHits] = useState([])
  const [status, setStatus] = useState('idle') // idle | loading | ok | error
  const [selected, setSelected] = useState(-1)
  const [detailPk, setDetailPk] = useState(null) // 只在点击具体结果后才有值 → 右栏才出现
  const [overlay, setOverlay] = useState(false) // 窄屏时预览浮层是否展开

  /* 切页面（首页/搜索/目录/时间线）即收起右栏详情——详情属于某个页面的
     上下文，跨页面挂着没有意义（2026-09-22 用户反馈）。 */
  useEffect(() => { setDetailPk(null) }, [mode])

  const [stats, setStats] = useState(null)
  const [offline, setOffline] = useState(false)
  const [sideOpen, setSideOpen] = useState(() => {
    // 侧栏开合记入 localStorage（用户要求可收起且记住）；没存过则桌面展开/窄屏收起
    const saved = lsGet('side')
    if (saved === '0' || saved === '1') return saved === '1'
    return !window.matchMedia(DRAWER_QUERY).matches
  })
  const toggleSide = useCallback(() => {
    setSideOpen((v) => {
      lsSet('side', v ? '0' : '1')
      return !v
    })
  }, [])
  const [treePath, setTreePath] = useState([]) // 目录页：从磁盘根到当前目录的链
  const [month, setMonth] = useState('') // 时间线选中的月份

  const inputRef = useRef(null)
  const reqId = useRef(0)
  const debouncedQ = useDebounced(q, 160)
  const narrow = useMediaQuery(NARROW_QUERY)
  const isSearch = mode === 'search'
  const tab = mode === 'home' ? 'home' : 'portal'

  /* 搜索的唯一出口（规格 §7）——筛选变化也从这里走，不在各自的
     事件回调里各发各的请求。

     竞态（规格 §9）：每次请求递增 reqId，响应回来时对不上就整包丢弃。
     高频词冷查要 1.9s，用户改词后的快响应先回来、慢的后到，
     没有这道闸门就会用旧查询的结果覆盖新查询的结果。 */
  const search = useCallback(async (query, ex, tm, dr) => {
    const id = ++reqId.current
    setStatus('loading')
    try {
      const data = await apiGet('/search', {
        q: query, ext: ex, dir_: dr, ...timeRange(tm),
      })
      if (id !== reqId.current) return
      const list = data.hits || []
      setHits(list)
      setStatus('ok')
      setSelected(list.length ? 0 : -1) // 高亮第一条（规格 §5），但不自动开右栏
      setOverlay(false) // 窄屏不因为一次搜索就弹浮层
    } catch {
      if (id !== reqId.current) return
      setHits([])
      setStatus('error')
      setSelected(-1)
    }
  }, [])

  /* 无查询 = 无结果列表（2026-09-22 简化要求）：空态只有搜索框和筛选，
     不发请求、不出列表——首屏干净，有查询才渐进展开。 */
  const hasQuery = Boolean(debouncedQ.trim())
  useEffect(() => {
    if (!isSearch) return
    if (!hasQuery) {
      reqId.current += 1 // 作废在途请求
      setHits([]); setStatus('idle'); setSelected(-1)
      return
    }
    search(debouncedQ, ext, time, dir)
  }, [isSearch, hasQuery, debouncedQ, ext, time, dir, search])

  // 索引状态：轮询失败即离线。以前 .then 不接 catch，
  // 后端挂掉时页面只是"无结果"，看起来像库里没东西——误导性太强。
  useEffect(() => {
    let alive = true
    const load = () => apiGet('/stats')
      .then((s) => { if (alive) { setStats(s); setOffline(false) } })
      .catch(() => { if (alive) setOffline(true) })
    load()
    const t = setInterval(load, 10000)
    return () => { alive = false; clearInterval(t) }
  }, [])

  /* 会话心跳 Worker（2026-09-22）：普通页面定时器会被浏览器按可见性节流
     （后台标签 5 分钟后降到 1/分钟），人离开 >2.5 分钟心跳就断、看门狗会
     停服务。专用 Worker 的定时器不受节流——离开多久心跳都不断。 */
  useEffect(() => {
    let w
    try {
      const src = "setInterval(()=>fetch('/api/ping',{method:'POST'}).catch(()=>{}),10000)"
      w = new Worker(URL.createObjectURL(new Blob([src], { type: 'text/javascript' })))
    } catch { /* Worker 不可用就退化为仅页面内轮询 */ }
    return () => w?.terminate()
  }, [])

  /* 状态 → URL。写的是 q 的防抖值：每敲一个字都塞一条历史，后退键就废了。
     首屏那次用 replaceState（别为初始状态多留一条），之后变化才进历史。 */
  const firstUrl = useRef(true)
  useEffect(() => {
    const want = buildHash({ mode, q: debouncedQ, ext, time, dir })
    if (want === window.location.hash) { firstUrl.current = false; return }
    if (firstUrl.current) history.replaceState(null, '', want)
    else history.pushState(null, '', want)
    firstUrl.current = false
  }, [mode, debouncedQ, ext, time, dir])

  /* URL → 状态（后退/前进）。pushState 不触发 hashchange，所以监听 popstate。
     设完状态后上面那个 effect 会发现 want === location.hash 而不再写一次。 */
  useEffect(() => {
    const onPop = () => {
      const s = parseHash()
      setMode(s.mode || 'home')
      setQ(s.q)
      setExt(normExt(s.ext))
      setTime(s.time)
      setDir(s.dir)
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const selectAt = useCallback((i) => {
    setSelected(i)
  }, [])

  /* 右栏只在「点了具体结果」后出现（2026-09-21 改版要求）——
     键盘移动只改高亮，不再自动更新右栏。 */
  const onRowClick = useCallback((i) => {
    const hit = hits[i]
    if (!hit) return
    recordClick(hit.pk, 'detail', q)
    setSelected(i)
    setDetailPk(hit.pk)
    if (narrow) setOverlay(true)
  }, [hits, q, narrow])

  const activate = useCallback((hit) => {
    if (!hit) return
    recordClick(hit.pk, 'open', q)
    apiPost('/open', { pk: hit.pk, mode: 'open' }).catch(() => {})
  }, [q])

  const onLocate = useCallback((hit) => {
    recordClick(hit.pk, 'locate', q)
    apiPost('/open', { pk: hit.pk, mode: 'locate' }).catch(() => {})
  }, [q])

  const openExternal = useCallback(({ pk }) => {
    setDetailPk(pk)
    if (narrow) setOverlay(true)
  }, [narrow])

  /* 目录树的出口：限定到某个目录再搜。走的是搜索现有的 dir_ 前缀过滤，
     不新增接口——所以这一条把「点一个文件夹 → 只搜这里」真正打通了。 */
  const onlyThisDir = useCallback((path) => {
    setDir(path)
    setMode('search')
  }, [])

  useHotkeys((e) => {
    const key = e.key
    if ((e.ctrlKey || e.metaKey) && key.toLowerCase() === 'k') {
      e.preventDefault()
      if (mode === 'home') setMode('search')
      inputRef.current?.focus()
      inputRef.current?.select()
      return
    }
    if (key === 'Escape') {
      if (q) { setQ(''); inputRef.current?.focus() }
      else if (document.activeElement === inputRef.current) inputRef.current.blur()
      else if (narrow && overlay) setOverlay(false)
      else if (detailPk) setDetailPk(null) // 点空白/Esc 收右栏
      return
    }
    if (!isSearch) return
    if (key === 'ArrowDown' || key === 'ArrowUp' || key === 'PageDown' || key === 'PageUp') {
      if (!hits.length) return
      e.preventDefault() // 否则方向键会滚动列表
      const step = { ArrowDown: 1, ArrowUp: -1, PageDown: 10, PageUp: -10 }[key]
      selectAt(Math.min(hits.length - 1, Math.max(0, selected < 0 ? 0 : selected + step)))
      return
    }
    if (key === 'Enter' && selected >= 0) activate(hits[selected])
  })

  const pill = pillOf(offline, stats)

  const total = fmtNum(stats?.files)
  const headText = status === 'loading'
    ? '搜索中…'
    : hits.length >= RESULT_CAP
      ? `显示前 ${RESULT_CAP} 条 · 共 ${total} 已索引` // 后端还没有总数，只给前 N 条
      : `匹配到 ${fmtNum(hits.length)} 个文件 · 共 ${total} 已索引`

  /* 激活的筛选（时间/类型/目录）：结果状态行常显 + 空结果时提示原因。
     静默的筛选器会"无声地杀掉结果"（2026-09-22 实案：近 1 年筛掉全部
     老文件，用户以为搜索坏了），所以筛选必须可见、可一键清除。 */
  const activeFilters = []
  if (time) {
    activeFilters.push(['时间', TIME_OPTIONS.find(([k]) => k === time)?.[1] || time])
  }
  if (ext) {
    activeFilters.push(['类型', TYPE_OPTIONS.find(([k]) => k === ext)?.[1] || ext])
  }
  if (dir) activeFilters.push(['目录', dir])
  const clearFilters = useCallback(() => { setExt(''); setTime(''); setDir('') }, [])

  const goTab = useCallback((t) => {
    setMode(t === 'home' ? 'home' : (mode === 'home' ? 'search' : mode))
  }, [mode])

  /* 侧栏图标栏模式（2026-09-22）：点当前维度图标 = 收起/展开；
     点其他维度图标 = 切到该维度并展开侧栏。 */
  const onModeIcon = useCallback((key) => {
    if (mode === key) {
      toggleSide()
    } else {
      setMode(key)
      if (!sideOpen) {
        lsSet('side', '1')
        setSideOpen(true)
      }
    }
  }, [mode, sideOpen, toggleSide])

  /* 点空白收起右栏（2026-09-22 要求）：命中白名单元素不动——行/文件行/
     树行/月份/预览栏本体/按钮/输入框/搜索框。其余一律视为空白。 */
  const onMainClick = useCallback((e) => {
    if (!e.target.closest(
        '.row, .file-row, .tree-row, .month-item, .preview, button, input, .hero-box')) {
      setDetailPk(null)
    }
  }, [])

  return (
    <div className={`app${sideOpen ? '' : ' side-closed'}`}>
      <TopBar tab={tab} onTab={goTab} pill={pill} />
      <div className="body">
        <SidePane
          mode={mode}
          onModeIcon={onModeIcon}
          open={sideOpen}
          ext={ext}
          onExt={setExt}
          time={time}
          onTime={setTime}
          dir={dir}
          onDir={setDir}
          treePath={treePath}
          onRootPick={(n) => setTreePath([n])}
          month={month}
          onMonth={setMonth}
        />
        <main className={`main${isSearch && !hasQuery ? ' search-idle' : ''}`} onClick={onMainClick}>
          {mode === 'home' && (
            <HomeView stats={stats} offline={offline} onGoSearch={() => setMode('search')} />
          )}
          {isSearch && (
            <div className="search-view">
              <div className={`hero${hasQuery ? '' : ' idle'}`}>
                <div className="hero-box">
                  <SearchGlyph />
                  <input
                    ref={inputRef}
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    placeholder="搜索文件名或正文内容…"
                    aria-label="搜索"
                  />
                  <button className="hero-btn" aria-label="搜索"
                          onClick={() => search(q, ext, time, dir)}>
                    <SearchGlyph />
                  </button>
                </div>
              </div>
              {/* 类型筛选横排在搜索框下面（改版要求）；时间/目录在左栏 */}
              <div className="chips">
                {TYPE_OPTIONS.map(([key, label]) => (
                  <button key={key || 'all'}
                          className={`type-chip${ext === key ? ' on' : ''}`}
                          onClick={() => setExt(key)}>
                    {key && (
                      <span className="cdot" style={{ background: catVar('.' + key) }} />
                    )}
                    {label}
                  </button>
                ))}
              </div>
              {hasQuery ? (
                <>
                  <div className="col-head">
                    <span>{headText}</span>
                    {/* 有结果才在状态行列筛选；零结果时原因和清除按钮在下方空态里，避免重复 */}
                    {activeFilters.length > 0 && hits.length > 0 && (
                      <span className="active-filters">
                        筛选：{activeFilters.map(([, label]) => label).join(' · ')}
                      </span>
                    )}
                  </div>
                  <ResultList
                    status={status}
                    hits={hits}
                    q={q}
                    selected={selected}
                    onSelect={onRowClick}
                    onActivate={activate}
                    onLocate={onLocate}
                    onRetry={() => search(debouncedQ, ext, time, dir)}
                    filters={activeFilters}
                    onClearFilters={clearFilters}
                  />
                </>
              ) : (
                <div className="scroll">
                  <div className="state">
                    <p className="main-line">输入关键词，检索你的知识库</p>
                    <p className="sub-line">Ctrl+K 随时回到搜索框 · 回车打开选中文件</p>
                  </div>
                </div>
              )}
            </div>
          )}
          {mode === 'tree' && (
            <TreeView
              treePath={treePath}
              onPick={setTreePath}
              onOpen={openExternal}
              onSearchHere={onlyThisDir}
              sideOpen={sideOpen}
            />
          )}
          {mode === 'time' && <TimelineView month={month} onOpen={openExternal} />}
        </main>
        {/* 右栏：只在点过具体结果后渲染（detailPk 非空） */}
        {!narrow && detailPk && <PreviewPane pk={detailPk} q={q} />}
        {narrow && overlay && detailPk && (
          <PreviewPane pk={detailPk} q={q} showClose onClose={() => setOverlay(false)} />
        )}
      </div>
    </div>
  )
}

function SearchGlyph() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none"
         stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5 14 14" strokeLinecap="round" />
    </svg>
  )
}
