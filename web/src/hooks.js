import { useEffect, useRef, useState } from 'react'

/** 防抖一个值。搜索框用（规格 §4.2：防抖 160ms）。 */
export function useDebounced(value, ms) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

/** 断点适配（规格 §2）：1200px 以下隐藏预览栏，860px 以下隐藏左栏。 */
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const onChange = (e) => setMatches(e.matches)
    mq.addEventListener('change', onChange)
    setMatches(mq.matches)
    return () => mq.removeEventListener('change', onChange)
  }, [query])
  return matches
}

/** 全局键盘操作（规格 §4.5）。
 *  handler 存在 ref 里，所以只挂一次监听、也不会拿到过期闭包——
 *  省掉让调用方维护依赖数组这件容易出错的事。 */
export function useHotkeys(handler) {
  const ref = useRef(handler)
  ref.current = handler
  useEffect(() => {
    const onKey = (e) => ref.current(e)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}
