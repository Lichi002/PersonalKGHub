import React, { useEffect, useRef, useState } from 'react'
import { catOf, extLabel, fmtSize, fmtTime } from '../format.js'

/** 命中来源：排序 v2 的三个信号（文件名 0.55 / 标签 0.45 / bm25 兜底）在
 *  后端算，卡片上标出来才知道「为什么排在这里」——这同时是排序的调试视图，
 *  出问题时一眼看出是文件名匹配错了还是标签拖了后腿。
 *
 *  正文命中用 snippet 判断（后端确实在正文里找到了词才生成摘要）；
 *  hit_fts 含路径名，去掉正文命中后剩下的就是路径命中（短查询的 LIKE 也走这条）。*/
function sources(hit) {
  const out = []
  if (hit.hit_name) out.push(['文件名命中', 'strong'])
  if (hit.hit_tags) out.push(['标签命中', 'strong'])
  if (hit.snippet) out.push(['正文命中', ''])
  else if (hit.hit_fts) out.push(['路径命中', 'weak'])
  return out.slice(0, 3)
}

/** 后端在命中词两侧打了 [[ ]] 标记（api._snippet），这里转成 <mark>。 */
function Snippet({ text }) {
  if (!text) return null
  const parts = text.split(/\[\[|\]\]/)
  return (
    <p className="row-snippet">
      {parts.map((p, i) => (i % 2 ? <mark key={i}>{p}</mark> : <span key={i}>{p}</span>))}
    </p>
  )
}

function Skeleton() {
  // 宽度错开一点，比五条等长灰条更像真列表（规格 §4.7）
  const widths = ['38%', '26%', '44%', '31%', '40%']
  return (
    <div aria-hidden="true">
      {widths.map((w, i) => (
        <div className="skel-row" key={i}>
          <div className="skel-bar tall" />
          <div>
            <div className="skel-bar" style={{ width: w }} />
            <div className="skel-bar" style={{ width: '64%', marginTop: 8 }} />
          </div>
        </div>
      ))}
    </div>
  )
}

export default function ResultList({
  status, hits, q, selected, onSelect, onActivate, onLocate, onRetry,
  filters = [], onClearFilters,
}) {
  const [copied, setCopied] = useState(null)
  const scrollRef = useRef(null)

  // 选中行滚进可视区（键盘上下移动时必需，规格 §4.5）
  useEffect(() => {
    if (selected < 0) return
    scrollRef.current?.querySelector('.row.on')?.scrollIntoView({ block: 'nearest' })
  }, [selected])

  const copy = (e, hit) => {
    e.stopPropagation()
    navigator.clipboard?.writeText(hit.path)
    setCopied(hit.pk)
    setTimeout(() => setCopied((c) => (c === hit.pk ? null : c)), 1500)
  }

  // 首屏加载才铺骨架：已有结果时重搜索保留旧列表，避免高频输入下闪白
  if (status === 'loading' && hits.length === 0) {
    return <div className="scroll"><Skeleton /></div>
  }

  if (status === 'error') {
    return (
      <div className="scroll">
        <div className="state">
          <p className="main-line">搜索服务暂时不可用</p>
          <p className="sub-line">后端没响应，右上角状态点会是红色</p>
          <button className="retry" onClick={onRetry}>重试</button>
        </div>
      </div>
    )
  }

  if (!hits.length) {
    return (
      <div className="scroll">
        <div className="state">
          <p className="main-line">{q ? '没有找到匹配的文件' : '库里还没有可搜索的文件'}</p>
          {/* 有筛选时把原因摊开说 + 一键清除：静默的筛选器最像"搜索坏了" */}
          {filters.length > 0 ? (
            <>
              <p className="sub-line">
                当前筛选：{filters.map(([k, label]) => `${k}=${label}`).join(' · ')}
              </p>
              <button className="retry" onClick={onClearFilters}>清除全部筛选</button>
            </>
          ) : (
            <p className="sub-line">{q ? '换个说法，或清掉左侧筛选再试' : '等提取完成，或检查采集器是否在跑'}</p>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="scroll" ref={scrollRef}>
      {hits.map((hit, i) => (
        <div
          key={hit.pk}
          className={`row${i === selected ? ' on' : ''}`}
          style={{ animationDelay: `${Math.min(i * 15, 240)}ms` }}
          onClick={() => onSelect(i)}
          onDoubleClick={() => onActivate(hit)}
        >
          <span className={`chip-type ${catOf(hit.ext)}`}>{extLabel(hit.ext)}</span>
          <div>
            <div className="row-top">
              <span className="row-name" title={hit.name}>{hit.name}</span>
              <span className="row-badges">
                {sources(hit).map(([label, tone]) => (
                  <span key={label} className={`badge src${tone ? ' ' + tone : ''}`}>
                    {label}
                  </span>
                ))}
                {hit.scanned && <span className="badge scanned">扫描件</span>}
                {/* 排序分只在有查询时才有意义（空查询是按时间倒序）。
                    hover 才看得见细节，平时不打扰。 */}
                {q && hit.score != null && (
                  <span className="badge score" title="排序分 = 文件名/标签相似度 + 0.5×bm25 百分位×(1−相似度)">
                    {hit.score.toFixed(2)}
                  </span>
                )}
              </span>
              <span className="row-actions">
                <button className="row-action" onClick={(e) => { e.stopPropagation(); onLocate(hit) }}>
                  所在文件夹
                </button>
                <button className="row-action" onClick={(e) => copy(e, hit)}>
                  {copied === hit.pk ? '已复制' : '复制路径'}
                </button>
              </span>
            </div>
            <div className="row-meta">
              <span className="row-path" title={hit.path}>{hit.path}</span>
              <span>{fmtTime(hit.mtime)}</span>
              <span>{fmtSize(hit.size)}</span>
            </div>
            <Snippet text={hit.snippet} />
          </div>
        </div>
      ))}
    </div>
  )
}
