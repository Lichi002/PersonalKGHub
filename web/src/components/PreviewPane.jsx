import React, { useEffect, useState } from 'react'
import { apiGet, apiPost, recordClick } from '../api.js'
import { fmtSize, fmtTime, STATUS_LABEL } from '../format.js'

/** [[ ]] 标记转 <mark>（与 ResultList 的 Snippet 同源逻辑）。 */
function Marked({ text }) {
  const parts = text.split(/\[\[|\]\]/)
  return (
    <>
      {parts.map((p, i) => (i % 2 ? <mark key={i}>{p}</mark> : <span key={i}>{p}</span>))}
    </>
  )
}

/** 右栏 300px（规格 §4.6）：元数据 + 标签 + 命中位置 + 正文预览 + 操作。
 *  命中位置（2026-09-22 加，参考版 hit-card）：带查询词点开时显示正文
 *  命中次数与多条上下文——比单条摘要信息量大。窄屏变浮层，靠 onClose 收起。 */
export default function PreviewPane({ pk, q = '', showClose, onClose }) {
  const [doc, setDoc] = useState(null)
  const [preview, setPreview] = useState(null)
  const [err, setErr] = useState(null)
  const [copied, setCopied] = useState(false)
  const query = q.trim()

  useEffect(() => {
    if (!pk) return
    let alive = true
    setDoc(null); setPreview(null); setErr(null); setCopied(false)
    apiGet(`/doc/${pk}`)
      .then((d) => { if (alive) (d.error ? setErr('文件已不存在') : setDoc(d)) })
      .catch(() => alive && setErr('详情加载失败'))
    apiGet(`/preview/${pk}`, query ? { q: query } : {})
      .then((p) => alive && setPreview(p))
      .catch(() => alive && setPreview({ text: '', reason: '预览加载失败' }))
    return () => { alive = false }
  }, [pk, query])

  if (!pk) {
    return (
      <div className="preview">
        <p className="preview-empty">选择左侧文件查看详情</p>
      </div>
    )
  }

  const open = (mode) => {
    recordClick(pk, mode === 'open' ? 'open' : 'locate', q)
    apiPost('/open', { pk, mode }).catch(() => {})
  }

  const copy = () => {
    navigator.clipboard?.writeText(doc?.path || '')
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="preview">
      {showClose && <button className="preview-close" onClick={onClose}>× 收起</button>}

      {err && <p className="preview-empty">{err}</p>}
      {!err && !doc && <p className="preview-empty">加载中…</p>}

      {doc && (
        <>
          <h2 className="pv-name">{doc.name}</h2>
          <div className="pv-rows">
            <div className="pv-row"><span className="k">路径</span><span className="v mono">{doc.path}</span></div>
            <div className="pv-row"><span className="k">类型</span><span className="v">{(doc.ext || '').replace('.', '').toUpperCase()}</span></div>
            <div className="pv-row"><span className="k">大小</span><span className="v">{fmtSize(doc.size)}</span></div>
            <div className="pv-row"><span className="k">修改时间</span><span className="v">{fmtTime(doc.mtime)}</span></div>
            <div className="pv-row"><span className="k">状态</span><span className="v">{STATUS_LABEL[doc.status] || doc.status}{doc.scanned ? ' · 扫描件（未 OCR）' : ''}</span></div>
          </div>

          {doc.tags?.length > 0 && (
            <div className="pv-tags">
              {doc.tags.map((t) => <span className="tag" key={t}>{t}</span>)}
            </div>
          )}

          <div className="pv-actions">
            <button className="btn primary" onClick={() => open('open')}>打开文件</button>
            <button className="btn" onClick={() => open('locate')}>所在文件夹</button>
          </div>
          <div className="pv-actions">
            <button className="btn" onClick={copy}>{copied ? '已复制' : '复制路径'}</button>
          </div>

          {preview?.contexts?.length > 0 && (
            <div className="pv-hits">
              <h4>命中位置（正文出现 {preview.match_count} 次）</h4>
              <div className="hit-card">
                {preview.contexts.map((c, i) => (
                  <p className="pv-ctx" key={i}><Marked text={c} /></p>
                ))}
              </div>
            </div>
          )}

          <div className="pv-preview">
            <h4>内容预览</h4>
            {!preview && <p className="preview-empty">加载中…</p>}
            {preview && !preview.text && (
              <p className="preview-empty">{preview.reason || '无预览内容'}</p>
            )}
            {preview?.text && (
              <>
                <pre className="preview-text">{preview.text}</pre>
                {preview.truncated && <p className="hint">仅显示前 5000 字 · 打开文件看全文</p>}
              </>
            )}
          </div>
        </>
      )}
    </div>
  )
}
