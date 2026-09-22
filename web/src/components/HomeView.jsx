import React from 'react'
import { catOf, catVar, extLabel, fmtNum } from '../format.js'

const DocsIcon = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor"
       strokeWidth="1.5" aria-hidden="true">
    <path d="M3 1.5h7L13 4.5V14.5H3V1.5Z" /><path d="M10 1.5V4.5H13" />
  </svg>
)
const ChartIcon = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor"
       strokeWidth="1.5" aria-hidden="true">
    <path d="M2 13.5h12" strokeLinecap="round" />
    <path d="M4 13.5V9M8 13.5V4.5M12 13.5V6.5" strokeLinecap="round" />
  </svg>
)
const SyncIcon = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor"
       strokeWidth="1.5" aria-hidden="true">
    <path d="M13.5 8a5.5 5.5 0 0 1-9.4 3.9M2.5 8a5.5 5.5 0 0 1 9.4-3.9" strokeLinecap="round" />
    <path d="M2.5 14v-2.5H5M13.5 2v2.5H11" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)
const BulbIcon = () => (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor"
       strokeWidth="1.5" aria-hidden="true">
    <path d="M8 1.5a4.5 4.5 0 0 1 2.5 8.2c-.5.4-1 1-1 1.8h-3c0-.8-.5-1.4-1-1.8A4.5 4.5 0 0 1 8 1.5Z" />
    <path d="M6.5 14h3" strokeLinecap="round" />
  </svg>
)

/** 首页（2026-09-21 改版）：知识库的数量、构成、更新方式、使用说明。
 *  参考豆包首页的卡片网格：浅卡、图标 + 短句，不放长篇大论。 */
export default function HomeView({ stats, offline, onGoSearch }) {
  const byExt = Object.entries(stats?.by_ext || {}).sort((a, b) => b[1] - a[1])
  const totalFiles = stats?.files || byExt.reduce((s, [, n]) => s + n, 0)
  const extracted = stats?.by_status?.extracted || 0
  const failed = stats?.by_status?.failed || 0
  const pending = stats?.by_status?.pending || 0

  return (
    <div className="home">
      <div className="home-inner">
        <h2>你的个人知识库</h2>
        <p className="sub">
          自动收录本机的文档、表格、演示与笔记，提取正文并生成标签，随时搜索和预览。
        </p>

        <div className="home-cards">
          <div className="hcard hcard-files">
            <div className="hhead">
              <div className="hicon"><DocsIcon /></div>
              <h4>收录文件</h4>
            </div>
            <div className="big">{fmtNum(stats?.files)}<span className="unit"> 个</span></div>
            <p className="sub">
              已提取正文 {fmtNum(extracted)} · 待处理 {fmtNum(pending)} · 不支持 {fmtNum(failed)}
            </p>
            {offline && <p className="warn-line">索引服务未连接，数字可能不是最新的</p>}
          </div>

          <div className="hcard hcard-ext">
            <div className="hhead">
              <div className="hicon"><ChartIcon /></div>
              <h4>类型构成</h4>
            </div>
            {byExt.length ? byExt.slice(0, 6).map(([e, n]) => (
              <div className="ext-row" key={e}
                   title={`${extLabel(e)}：${fmtNum(n)} / ${fmtNum(totalFiles)} 个，占 ${((n / totalFiles) * 100).toFixed(1)}%`}>
                <span className="lbl">{extLabel(e)}</span>
                {/* 轨道 = 文件总数（类别色 18% 浅底），填充段 = 当前类别数（60% 深色）
                    ——重叠区比浅底明显更深，一眼可辨 */}
                <span className="track"
                      style={{ background: `color-mix(in srgb, ${catVar(e)} 18%, transparent)` }}>
                  <i style={{
                    width: `${Math.max(2, (n / totalFiles) * 100)}%`,
                    background: `color-mix(in srgb, ${catVar(e)} 60%, transparent)`,
                  }} />
                </span>
                <span className="n">{fmtNum(n)}/{fmtNum(totalFiles)}</span>
              </div>
            )) : (
              <p className="sub">{stats ? '暂无数据' : '加载中…'}</p>
            )}
          </div>

          <div className="hcard hcard-sync">
            <div className="hhead">
              <div className="hicon"><SyncIcon /></div>
              <h4>保持最新</h4>
            </div>
            <ul>
              <li>采集器开机自启，盯住 C 盘常用目录与整个 D 盘</li>
              <li>文件新建、修改、删除，几秒内自动进索引</li>
              <li>正文自动提取，标签自动生成，无需手工维护</li>
            </ul>
            {stats?.collector_connected === false && (
              <p className="warn-line">采集器当前未运行，索引暂停更新</p>
            )}
          </div>

          <div className="hcard hcard-tip">
            <div className="hhead">
              <div className="hicon"><BulbIcon /></div>
              <h4>怎么用</h4>
            </div>
            <ul>
              <li>进「知识搜索」，<kbd>Ctrl K</kbd> 随时聚焦搜索框</li>
              <li>目录页选中文件夹，点「只搜这里」限定范围</li>
              <li>点击结果在右侧预览正文；「打开文件」直达原文件</li>
              <li>搜索词会标出命中来源：文件名 / 标签 / 正文</li>
            </ul>
          </div>
        </div>

        <div className="home-cta">
          <button onClick={onGoSearch}>开始搜索</button>
        </div>
      </div>
    </div>
  )
}
