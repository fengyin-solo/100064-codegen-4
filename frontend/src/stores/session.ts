import { defineStore } from 'pinia'

/** 角色口径：前台只能登记访客；被访人只能审批本部门来访；门禁管理员受控发证与核销。 */
export type OperatorRole = '前台' | '被访人' | '门禁管理员'

export const ROLE_HEADER: Record<OperatorRole, string> = {
  前台: 'reception',
  被访人: 'host',
  门禁管理员: 'guard',
}

const STORAGE_KEY = 'lab-operator-v1'

interface OperatorState {
  operator: string
  role: OperatorRole
  department: string
  shiftLabel: string
  scope: string
}

function loadState(): OperatorState {
  const fallback: OperatorState = {
    operator: '前台小周',
    role: '前台',
    department: '检测一部',
    shiftLabel: '白班 08:00-20:00',
    scope: '实验室样品检测平台',
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return fallback
    return { ...fallback, ...(JSON.parse(raw) as Partial<OperatorState>) }
  } catch {
    return fallback
  }
}

export const useSessionStore = defineStore('session', {
  state: (): OperatorState => loadState(),
  getters: {
    canOperate: (state) => state.operator.length > 0,
    roleHeader: (state) => ROLE_HEADER[state.role] ?? '',
    isReception: (state) => state.role === '前台',
    isHost: (state) => state.role === '被访人',
    isGuard: (state) => state.role === '门禁管理员',
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setRole(role: OperatorRole) {
      this.role = role
      this.persist()
    },
    setDepartment(department: string) {
      this.department = department
      this.persist()
    },
    persist() {
      const { operator, role, department } = this
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ operator, role, department }))
    },
  },
})
