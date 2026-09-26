/** 统一请求封装：拼后端地址、抛网络错误、给页脚留一句可读的说明。 */
import { useSessionStore } from '@/stores/session'

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

interface OperatorHeaders {
  'X-Operator-Role'?: string
}

export function operatorHeaders(): OperatorHeaders {
  // 中文不进 HTTP 头：角色用英文别名，部门随提交体传递。
  const session = useSessionStore()
  return session.roleHeader ? { 'X-Operator-Role': session.roleHeader } : {}
}

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  return fetch(url, {
    headers: { 'Content-Type': 'application/json', ...operatorHeaders(), ...(init?.headers ?? {}) },
    ...init,
  }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}

export interface ActionResponse {
  ok: boolean
  message: string
  entry?: Record<string, unknown> | null
}

/** 提交业务动作：自动附带当前角色与所属部门；越权时错误里带后端给的拒绝原因。 */
export async function postAction(
  path: string,
  values: Record<string, unknown> = {},
): Promise<{ status: number; body: ActionResponse }> {
  const session = useSessionStore()
  const payload: Record<string, unknown> = { ...values }
  // 被访人的所属部门随提交体上传（部门名含中文，不能放进请求头）。
  if (session.isHost && payload.department === undefined) {
    payload.department = session.department
  }
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify({ values: payload }),
  })
  const body = (await response.json().catch(() => ({ ok: false, message: '服务返回无法解析' }))) as ActionResponse
  return { status: response.status, body }
}
