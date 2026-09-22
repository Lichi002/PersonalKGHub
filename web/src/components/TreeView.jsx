import React, { useEffect, useState } from 'react'
import { apiGet, recordClick } from '../api.js'
import { catOf, extLabel, fmtTime } from '../format.js'

/* 目录浏览（Finder 列式）：
 * 每一列 = 当前目录的「子目录 + 直接文件」混排（2026-09-22 改：不再把文件
 * 挪到最后一层的独立面板）；点子目录往右开新列，点文件开右栏详情。
 * 每列顶部：目录名 +「只搜这里」（显性入口，任意层级可设搜索范围）。 */

const ScopeIcon = () => (
  <svg width="12" height="12" viewBox="0 0 16 16" fill="none"
       stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
    <circle cx="7" cy="7" r="4.5" />
    <path d="M10.5 10.5 14 14" strokeLinecap="round" />
  </svg>
)

/** 一列 = node 的内容：子目录在前（可下钻），文件在后（可开详情）。 */
function DirColumn({ node, activeFrn, onPick, onOpen, onSearchHere }) {
  const [children, setChildren] = useState(null)
  const [files, setFiles] = useState(null)
  useEffect(() => {
    let alive = true
    setChildren(null); setFiles(null)
    apiGet('/tree', { vol: node.volume, frn: node.frn })
      .then((d) => { if (alive) setChildren(d.children || []) })
      .catch(() => { if (alive) setChildren([]) })
    apiGet('/dir_files', { vol: node.volume, frn: node.frn })
      .then((d) => { if (alive) setFiles(d.files || []) })
      .catch(() => { if (alive) setFiles([]) })
    return () => { alive = false }
  }, [node.volume, node.frn])

  // 根节点（/api/tree 的 roots）没有 path 字段，卷根路径就是 "X:\"
  const path = node.path || `${node.volume}\\`
  const loading = children === null || files === null
  const empty = !loading && children.length === 0 && files.length === 0

  return (
    <div className="tree-col">
      <div className="tree-col-head">
        <span className="tname" title={path}>{node.label || node.name}</span>
        <button className="tree-scope" title={`只搜 ${path}`}
                onClick={() => onSearchHere(path)}>
          <ScopeIcon />
          只搜这里
        </button>
      </div>
      {loading && <p className="hint">加载中…</p>}
      {empty && <p className="hint">（空目录）</p>}
      {children?.map((c) => (
        <div key={`d${c.volume}${c.frn}`}
             className={`tree-row${c.frn === activeFrn ? ' on' : ''}`}
             onClick={() => onPick(c)}>
          <span className="tname" title={c.name}>{c.label || c.name}</span>
          {c.files > 0 && <span className="count">{c.files}</span>}
        </div>
      ))}
      {files?.map((f) => (
        <div className="file-row" key={f.pk}
             onClick={() => { recordClick(f.pk, 'tree'); onOpen({ pk: f.pk }) }}>
          <span className={`chip-type ${catOf(f.ext)}`}>{extLabel(f.ext)}</span>
          <span className="name" title={f.name}>{f.name}</span>
          <span className="spacer" />
          <span className="meta">{fmtTime(f.mtime)}</span>
        </div>
      ))}
    </div>
  )
}

export default function TreeView({ treePath, onPick, onOpen, onSearchHere, sideOpen }) {
  if (!treePath.length) {
    return (
      <div className="state">
        <p className="main-line">从左侧选择一个磁盘开始浏览</p>
        <p className="sub-line">{sideOpen ? '' : '（点击左栏的目录图标展开）'}</p>
      </div>
    )
  }
  return (
    <div className="tree-cols">
      {treePath.map((node, i) => (
        <DirColumn
          key={`${node.volume}${node.frn}`}
          node={node}
          activeFrn={treePath[i + 1]?.frn}
          onPick={(c) => onPick([...treePath.slice(0, i + 1), c])}
          onOpen={onOpen}
          onSearchHere={onSearchHere}
        />
      ))}
    </div>
  )
}
