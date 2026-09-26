/** 统一请求封装：拼后端地址、抛网络错误、给页脚留一句可读的说明。 */
import { useSessionStore } from '@/stores/session'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  const session = useSessionStore()
  const headers = new Headers(init?.headers)
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (session.operator) {
    headers.set('X-Operator-Id', session.operator.id)
  }
  return fetch(url, { ...init, headers }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

/** POST 类动作：HTTP 401/403 与业务失败统一抛出带后端原因的 ApiError。 */
export async function postAction(path: string, values: Record<string, unknown>): Promise<unknown> {
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  const payload = (await response.json().catch(() => null)) as
    | { ok?: boolean; message?: string; entry?: unknown }
    | { detail?: string }
    | null
  if (!response.ok) {
    const detail = payload && 'detail' in payload ? payload.detail : `接口返回 ${response.status}，操作未生效`
    throw new ApiError(response.status, detail || '操作被拒绝')
  }
  if (payload && 'ok' in payload && payload.ok === false) {
    throw new ApiError(422, payload.message || '业务校验未通过')
  }
  return payload
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}
