const API = '/api'

/** 取数失败一律抛这个错——调用方据此进入 error 态。
 *  绝不能让「服务没响应」被伪装成「没有结果」，那是误导。 */
export class ApiError extends Error {
  constructor(path, status) {
    super(`请求失败：${path}（${status ? 'HTTP ' + status : '网络不可达'}）`)
    this.path = path
    this.status = status
  }
}

async function request(path, options) {
  let r
  try {
    r = await fetch(`${API}${path}`, options)
  } catch {
    throw new ApiError(path, 0) // 0 = 连不上（后端没起来）
  }
  if (!r.ok) throw new ApiError(path, r.status)
  return r.json()
}

/** 空串/null 的参数直接不发——后端的默认值就是"不限"。 */
export function apiGet(path, params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== '' && v != null),
  ).toString()
  return request(`${path}${qs ? '?' + qs : ''}`)
}

export function apiPost(path, body) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/** 点击埋点：即发即忘，失败不打扰用户。推荐排序的数据源，攒着先不用。 */
export function recordClick(pk, kind, q = '') {
  apiPost('/click', { pk, kind, q }).catch(() => {})
}
