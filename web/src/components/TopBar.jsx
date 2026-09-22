import React from 'react'

/** 门户 logo：知识图谱节点图（PersonalKGHub 的 KG 意象），
 *  蓝→靛渐变；顶节点实心、下两节点空心，形成层次。 */
const LogoIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <defs>
      <linearGradient id="logo-grad" x1="0" y1="0" x2="24" y2="24"
                      gradientUnits="userSpaceOnUse">
        <stop offset="0" stopColor="#3d7fe0" />
        <stop offset="1" stopColor="#8a63d2" />
      </linearGradient>
    </defs>
    <g stroke="url(#logo-grad)" strokeWidth="1.6">
      <path d="M12 6.2 5.8 16.8M12 6.2l6.2 10.6M5.8 16.8h12.4" />
    </g>
    <circle cx="12" cy="5" r="2.6" fill="url(#logo-grad)" />
    <circle cx="5.6" cy="17.6" r="2.1" fill="var(--surface)" stroke="url(#logo-grad)" strokeWidth="1.7" />
    <circle cx="18.4" cy="17.6" r="2.1" fill="var(--surface)" stroke="url(#logo-grad)" strokeWidth="1.7" />
  </svg>
)

/** 顶栏（2026-09-22）：书形 logo │ 个人知识门户 │ [首页|知识搜索] │ pill。
 *  收起侧栏的把手挪到侧栏右缘（side-handle），顶栏不再放功能按钮。 */
export default function TopBar({ tab, onTab, pill }) {
  return (
    <header className="topbar">
      <span className="logo" aria-hidden="true"><LogoIcon /></span>
      <h1>个人知识门户</h1>
      <nav className="tabs" aria-label="页面切换">
        <button className={`tab${tab === 'home' ? ' on' : ''}`} onClick={() => onTab('home')}>
          首页
        </button>
        <button className={`tab${tab === 'portal' ? ' on' : ''}`} onClick={() => onTab('portal')}>
          知识搜索
        </button>
      </nav>
      <span className="spacer" />
      <span className={`pill ${pill.cls}`} title={pill.title}>
        <span className="dot" />
        {pill.text}
      </span>
    </header>
  )
}
