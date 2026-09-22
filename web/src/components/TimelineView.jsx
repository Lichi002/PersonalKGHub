import React, { useEffect, useState } from 'react'
import { apiGet, recordClick } from '../api.js'
import { catOf, extLabel, fmtTime } from '../format.js'

/* 时间线（2026-09-21 改进点 2）：月份列表挪进左侧栏纵向展示，
 * 主区只显示选中月份的文件——月份导航常驻，中间不浪费。 */

export default function TimelineView({ month, onOpen }) {
  const [files, setFiles] = useState(null)
  useEffect(() => {
    if (!month) return
    let alive = true
    setFiles(null)
    apiGet('/timeline', { month })
      .then((d) => { if (alive) setFiles(d.files || []) })
      .catch(() => { if (alive) setFiles([]) })
    return () => { alive = false }
  }, [month])

  if (!month) {
    return (
      <div className="state">
        <p className="main-line">从左侧选择一个月份</p>
      </div>
    )
  }

  return (
    <div className="files-pane">
      <div className="files-head">
        <span className="hint">{month} 修改的文件</span>
      </div>
      {files === null && <p className="hint">加载中…</p>}
      {files != null && files.length === 0 && <p className="hint">这个月没有知识文件</p>}
      {files?.map((f) => (
        <div className="file-row" key={f.pk}
             onClick={() => { recordClick(f.pk, 'timeline'); onOpen({ pk: f.pk }) }}>
          <span className={`chip-type ${catOf(f.ext)}`}>{extLabel(f.ext)}</span>
          <span className="name" title={f.name}>{f.name}</span>
          <span className="spacer" />
          <span className="meta">{fmtTime(f.mtime)}</span>
        </div>
      ))}
    </div>
  )
}
