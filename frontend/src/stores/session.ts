import { defineStore } from 'pinia'

export type OperatorRole = 'reception' | 'host' | 'guard'

export type Operator = {
  id: string
  name: string
  role: OperatorRole
  department: string
}

const ROLE_LABELS: Record<OperatorRole, string> = {
  reception: '前台',
  host: '被访人',
  guard: '门禁管理员',
}

const STORAGE_KEY = 'lab.operatorId'

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: null as Operator | null,
    operators: [] as Operator[],
    shiftLabel: '白班 08:00-20:00',
    scope: '实验室样品检测平台',
  }),
  getters: {
    roleLabel(state): string {
      return state.operator ? ROLE_LABELS[state.operator.role] : '未选择'
    },
    isReception: (state) => state.operator?.role === 'reception',
    isHost: (state) => state.operator?.role === 'host',
    isGuard: (state) => state.operator?.role === 'guard',
    canOperate: (state) => state.operator !== null,
  },
  actions: {
    hydrate(operators: Operator[]) {
      this.operators = operators
      const savedId = window.localStorage.getItem(STORAGE_KEY)
      const matched = operators.find((item) => item.id === savedId)
      this.operator = matched ?? operators[0] ?? null
    },
    setOperator(operatorId: string) {
      this.operator = this.operators.find((item) => item.id === operatorId) ?? this.operator
      if (this.operator) {
        window.localStorage.setItem(STORAGE_KEY, this.operator.id)
      }
    },
    setShift(label: string) {
      this.shiftLabel = label
    },
  },
})

export { ROLE_LABELS }
