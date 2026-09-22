/* 前端回归测试：SSR 渲染真实组件 + 纯函数单测。
 * 跑法：npm test（在 web/ 下）。
 *
 * 为什么能这么测：App 的取数全在 useEffect 里，服务端渲染不执行副作用，
 * 所以 renderToString 得到的就是「给定 URL 的首屏」——正好是 hash 还原
 * 和卡片渲染要验的东西。不引入 jest/vitest：这套依赖本来就在（esbuild 随
 * Vite 一起装），够用了。
 *
 * 注意：别改成 --format=cjs。CJS 打包会把默认导出裹成 interop 对象，
 * React 会报 "Element type is invalid"，是被测代码之外的坑。 */
import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import esbuild from 'esbuild'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
/* 打包产物必须落在 web/ 里面：--packages=external 之后 Node 要自己解析
   react，放在系统临时目录里找不到 node_modules。退出时清掉。 */
const OUT = mkdtempSync(join(ROOT, '.tmp-ui-test-'))
process.on('exit', () => rmSync(OUT, { recursive: true, force: true }))

async function bundle(entry, name) {
  const outfile = join(OUT, name)
  await esbuild.build({
    entryPoints: [join(ROOT, entry)],
    outfile,
    bundle: true,
    format: 'esm',
    packages: 'external', // react 等运行时解析，不要打进产物
    logLevel: 'warning',
  })
  return import(pathToFileURL(outfile).href)
}

const mq = () => ({ matches: false, addEventListener() {}, removeEventListener() {} })

globalThis.window = {
  location: { hash: '' },
  matchMedia: mq,
  addEventListener() {},
  removeEventListener() {},
}
globalThis.history = { pushState() {}, replaceState() {} }

const React = (await import('react')).default
const { renderToString } = await import('react-dom/server')
const App = await bundle('src/App.jsx', 'App.mjs')

const { parseHash, buildHash } = App

let pass = 0
let fail = 0
const check = (name, ok, extra = '') => {
  if (ok) { pass++; console.log(`  ok   ${name}`) }
  else { fail++; console.log(`  FAIL ${name} ${extra}`) }
}

// ---------- 1. buildHash / parseHash 往返 ----------
console.log('=== 1. hash 往返（编码/中文/反斜杠/特殊字符）===')
const cases = [
  { mode: 'home', q: '', ext: '', time: '', dir: '' },
  { mode: 'search', q: '会议纪要', ext: '.docx', time: 'month', dir: '' },
  { mode: 'tree', q: '', ext: '', time: '', dir: '' },
  { mode: 'search', q: '', ext: '', time: '', dir: 'D:\\0724报销\\一般人员费用' },
  { mode: 'search', q: 'a&b=c d', ext: '', time: '', dir: 'C:\\Users\\demo\\#1' },
  { mode: 'time', q: '发票', ext: '', time: 'year', dir: '' },
]
for (const st of cases) {
  const h = buildHash(st)
  window.location.hash = h
  const back = parseHash()
  const same = JSON.stringify(back) === JSON.stringify(st)
  check(`${h}`, same, same ? '' : `往返不一致 ${JSON.stringify(back)}`)
}
// 旧书签 mode=timeline 归一成 time（时间线挪进侧栏后改了 key）
window.location.hash = '#/mode=timeline'
check('旧 mode=timeline 归一为 time', parseHash().mode === 'time')
// 空状态 = '#/'，不是空串
window.location.hash = buildHash({ mode: '', q: '', ext: '', time: '', dir: '' })
check('空状态得到 #/', window.location.hash === '#/', window.location.hash)
// 幂等：同一个状态写两次结果一样（否则 effect 会反复 push 历史）
const h1 = buildHash(cases[1])
check('buildHash 幂等', h1 === buildHash(cases[1]))
// 顺序稳定：key 顺序固定，handler 里的 want === location.hash 才比得中
check('key 顺序稳定', h1 === '#/mode=search&q=%E4%BC%9A%E8%AE%AE%E7%BA%AA%E8%A6%81&ext=.docx&time=month',
  h1)

// ---------- 2. 首屏按 URL 还原（真的渲染 App） ----------
console.log('\n=== 2. 首屏从 URL 还原（renderToString）===')
const render = (hash) => {
  window.location.hash = hash
  return renderToString(React.createElement(App.default))
}

let html = render('#/')
check('空 URL：落在首页', html.includes('你的个人知识库') && html.includes('home-cta'))
check('空 URL：顶栏「首页」tab 选中', /class="tab on"[^>]*>首页/.test(html))
check('空 URL：没有搜索框（搜索框在知识搜索页）', !html.includes('hero-box'))

html = render('#/mode=search')
check('知识搜索页：hero 搜索框为空', /class="hero-box"/.test(html) && /value=""/.test(html))
check('知识搜索页：类型 chips 横排', html.includes('type-chip') && html.includes('全部类型'))
check('知识搜索页：「知识搜索」tab 选中', /class="tab on"[^>]*>知识搜索/.test(html))
check('知识搜索页：右栏未出现（还没点结果）', !html.includes('preview'))

html = render('#/q=' + encodeURIComponent('会议纪要') + '&ext=.docx&time=month')
check('还原查询词到搜索框', html.includes('会议纪要'), html.slice(0, 200))
check('还原类型筛选（URL 带点 .docx 也要高亮 Word）',
  /class="type-chip on"[\s\S]{0,80}>Word</.test(html))
check('还原时间筛选（侧栏，近 1 个月高亮）',
  /class="filter-item on"[\s\S]{0,80}近 1 个月/.test(html))

html = render('#/mode=tree')
check('目录页：主区提示从侧栏选磁盘', html.includes('从左侧选择一个磁盘'))
check('目录页：侧栏导航「目录」高亮',
  /<button class="on"[^>]*><svg[\s\S]*?<\/svg><span class="label">目录<\/span><\/button>/.test(html))

html = render('#/mode=time')
check('时间线：主区提示选月份', html.includes('从左侧选择一个月份'))
check('时间线：侧栏导航「时间线」高亮',
  /<button class="on"[^>]*><svg[\s\S]*?<\/svg><span class="label">时间线<\/span><\/button>/.test(html))

const dpath = 'D:\\0724报销\\一般人员'
html = render('#/dir=' + encodeURIComponent(dpath))
check('还原目录筛选：侧栏显示且可清除', html.includes('0724报销') && html.includes('点击清除'))

html = render('#/q=' + encodeURIComponent('x') + '&dir=')
check('dir 为空时侧栏显示未限定提示', html.includes('未限定'))

// 畸形 hash 不能白屏
for (const bad of ['#/', '#//', '#/q', '#/%', '#/q=%E4%BC', '#?q=a', '#/mode=nonsense']) {
  try {
    const h = render(bad)
    check(`畸形 hash 不炸：${bad}`, h.includes('topbar'))
  } catch (e) {
    check(`畸形 hash 不炸：${bad}`, false, e.message)
  }
}

// ---------- 3. 结果卡片的三来源徽章（组件级） ----------
console.log('\n=== 3. 命中来源徽章 ===')
const RL = (await bundle('src/components/ResultList.jsx', 'ResultList.mjs')).default
const hit = (o) => ({
  pk: 'C:1', name: 'a.docx', path: 'C:\\a.docx', ext: '.docx',
  size: 100, mtime: 1700000000, scanned: false, snippet: null, ...o,
})
const list = (hits, q = 'x') => renderToString(
  React.createElement(RL, {
    status: 'ok', hits, q, selected: 0,
    onSelect() {}, onActivate() {}, onLocate() {}, onRetry() {},
  }))

html = list([hit({ hit_name: true, hit_tags: true, hit_fts: true, snippet: '正文[[x]]' })])
check('三来源齐全时都标出',
  html.includes('文件名命中') && html.includes('标签命中') && html.includes('正文命中'))

html = list([hit({ hit_name: false, hit_tags: false, hit_fts: true, snippet: null })])
check('只有路径命中', html.includes('路径命中') && !html.includes('正文命中'))

html = list([hit({ hit_name: false, hit_tags: false, hit_fts: false, snippet: null })])
check('无来源时不出徽章', !html.includes('命中'))

html = list([hit({ hit_name: true, hit_tags: false, hit_fts: true, snippet: null, score: 0.575 })])
check('排序分显示（2 位）', html.includes('>0.57<'), html.match(/badge score[^<]*>([^<]*)/)?.[1])

html = list([hit({ hit_name: true, hit_tags: true, hit_fts: true, snippet: 'a', score: 0.5 })], '')
check('空查询不显示排序分', !html.includes('badge score'))
check('空查询仍显示命中来源', html.includes('文件名命中'))
check('超过 3 个来源被截断', (html.match(/badge src/g) || []).length <= 3)

// ---------- 4. 状态 pill 的四态（纯函数） ----------
console.log('\n=== 4. pill 优先级 ===')
const { pillOf } = await bundle('src/format.js', 'format.mjs')
const P = (offline, stats) => pillOf(offline, stats)
const eq = (name, got, wantCls, wantIn) => check(name,
  got.cls === wantCls && got.text.includes(wantIn), `${got.cls}/${got.text}`)

eq('离线压过一切', P(true, { collector_connected: false, by_status: { pending: 9 } }),
  'off', '未连接')
eq('采集器掉线压过提取中',
  P(false, { collector_connected: false, by_status: { pending: 9 }, files: 10 }),
  'warn', '采集器未运行')
eq('采集器正常 + 有积压', P(false, { collector_connected: true, by_status: { pending: 42 } }),
  'busy', '42')
eq('采集器正常 + 无积压', P(false, { collector_connected: true, by_status: {}, files: 5996 }),
  'ok', '5,996')
// 旧后端（没有 collector_connected 字段）不能被冤枉成掉线
eq('字段缺失 = 不知道，不报掉线', P(false, { by_status: {}, files: 1 }), 'ok', '1')
eq('字段为 null 也不报', P(false, { collector_connected: null, files: 1 }), 'ok', '1')
eq('stats 还没到（首屏）', P(false, null), 'ok', '0')
check('掉线态带 title 解释（查到原因）',
  (P(false, { collector_connected: false }).title || '').includes('PersonalKGHub-Collector'), ''
)
check('其余态不带 title', !P(true, null).title && !P(false, { files: 1 }).title)

rmSync(OUT, { recursive: true, force: true })
console.log(`\n通过 ${pass} / 失败 ${fail}`)
process.exit(fail ? 1 : 0)
