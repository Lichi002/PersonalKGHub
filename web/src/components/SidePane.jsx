import React, { useEffect, useState } from 'react'
import { apiGet } from '../api.js'
import { TIME_OPTIONS } from '../format.js'

const SearchIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor"
       strokeWidth="1.5" aria-hidden="true">
    <circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5 14 14" strokeLinecap="round" />
  </svg>
)
const FolderIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor"
       strokeWidth="1.5" aria-hidden="true">
    <path d="M1.5 4a1.5 1.5 0 0 1 1.5-1.5h3l1.5 2H13A1.5 1.5 0 0 1 14.5 6v6A1.5 1.5 0 0 1 13 13.5H3A1.5 1.5 0 0 1 1.5 12V4Z" />
  </svg>
)
const ClockIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor"
       strokeWidth="1.5" aria-hidden="true">
    <circle cx="8" cy="8" r="6" /><path d="M8 4.5V8l2.5 1.5" strokeLinecap="round" />
  </svg>
)

const MODES = [
  ['search', '搜索', SearchIcon],
  ['tree', '目录', FolderIcon],
  ['time', '时间线', ClockIcon],
]

/** 侧栏（2026-09-22 图标栏模式）：三个模式图标常驻——
 *  点当前维度图标 = 收起（缩成 56px 纯图标栏）；点其他维度图标 = 切换并展开。
 *  展开时下方展示该维度的具体内容（时间/目录筛选、磁盘根、月份列表）。 */
export default function SidePane({
  mode, onModeIcon, open,
  ext, onExt, time, onTime, dir, onDir,
  treePath, onRootPick,
  month, onMonth,
}) {
  const [roots, setRoots] = useState([])
  const [months, setMonths] = useState(null)

  // 磁盘根级：进目录模式才拉（懒加载，且只有两个卷）
  useEffect(() => {
    if (mode !== 'tree' || roots.length) return
    apiGet('/tree').then((d) => setRoots(d.children || [])).catch(() => setRoots([]))
  }, [mode, roots.length])

  // 月份：进时间线模式才拉；拉到后若还没选中月份，自动选最近一个月
  useEffect(() => {
    if (mode !== 'time' || months) return
    apiGet('/timeline')
      .then((d) => {
        const ms = d.months || []
        setMonths(ms)
        if (!month && ms.length) onMonth(ms[0].month)
      })
      .catch(() => setMonths([]))
  }, [mode, months, month, onMonth])

  return (
    <aside className={`side${open ? '' : ' closed'}`}>
      <div className="side-inner">
        <nav className="modes" aria-label="模式">
          {MODES.map(([key, label, Icon]) => (
            <button key={key}
                    className={mode === key ? 'on' : ''}
                    title={label}
                    onClick={() => onModeIcon(key)}>
              <Icon />
              <span className="label">{label}</span>
            </button>
          ))}
        </nav>
        <div className="side-scroll">
          {mode === 'search' && (
            <>
              <div className="group">
                <h3>修改时间</h3>
                {TIME_OPTIONS.map(([key, label]) => (
                  <div key={key || 'any'} className={`filter-item${time === key ? ' on' : ''}`}
                       onClick={() => onTime(key)}>
                    <span>{label}</span>
                  </div>
                ))}
              </div>
              <div className="group">
                <h3>目录</h3>
                {/* 目录限定的入口在目录页的「只搜这里」，这里只显示与清除 */}
                {dir ? (
                  <div className="filter-item on" onClick={() => onDir('')}
                       title={`${dir}（点击清除）`}>
                    <span className="ellipsis">{dir}</span>
                    <span className="x" aria-hidden="true">×</span>
                  </div>
                ) : (
                  <p className="hint">未限定。在「目录」页点文件夹可只搜那一个目录。</p>
                )}
              </div>
            </>
          )}
          {mode === 'tree' && (
            <div className="group">
              <h3>磁盘</h3>
              {roots.map((r) => (
                <div key={`${r.volume}${r.frn}`}
                     className={`filter-item${treePath[0]?.frn === r.frn ? ' on' : ''}`}
                     onClick={() => onRootPick(r)}>
                  <span>{r.label || r.name}</span>
                </div>
              ))}
              {roots.length === 0 && <p className="hint">加载中…</p>}
            </div>
          )}
          {mode === 'time' && (
            <div className="group">
              <h3>月份</h3>
              {(months || []).map((m) => (
                <div key={m.month} className={`month-item${month === m.month ? ' on' : ''}`}
                     onClick={() => onMonth(m.month)}>
                  <span>{m.month}</span>
                  <span className="n">{m.count}</span>
                </div>
              ))}
              {months != null && months.length === 0 && <p className="hint">还没有可显示的月份</p>}
              {months == null && <p className="hint">加载中…</p>}
            </div>
          )}
          {mode !== 'search' && mode !== 'tree' && mode !== 'time' && (
            <p className="hint">选择一个模式开始浏览。</p>
          )}
        </div>
      </div>
    </aside>
  )
}
