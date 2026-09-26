<template>
  <div class="app-shell">
    <aside class="app-side">
      <h1 class="app-title">实验室样品检测平台</h1>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="app-main">
      <header class="app-head">
        <span class="head-desc">面向样品受理、任务派发、检测执行、仪器校准与报告出具的一体化实验室检测管理后台。</span>
        <span class="head-user">
          当前值班：{{ store.operator ? store.operator.name : '未选择' }}
          <em v-if="store.operator" class="head-role">
            {{ store.roleLabel }} · {{ store.operator.department }}
          </em>
          · {{ store.shiftLabel }}
          <label class="identity-switch">
            切换身份
            <select
              class="identity-select"
              :value="store.operator?.id ?? ''"
              @change="onSwitch(($event.target as HTMLSelectElement).value)"
            >
              <optgroup v-for="group in groupedOperators" :key="group.role" :label="group.label">
                <option v-for="op in group.items" :key="op.id" :value="op.id">
                  {{ op.name }}（{{ op.department }}）
                </option>
              </optgroup>
            </select>
          </label>
        </span>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'

import { fetchJson } from '@/api/client'
import { ROLE_LABELS, useSessionStore, type Operator, type OperatorRole } from '@/stores/session'

const store = useSessionStore()

const navItems = [{ label: "运营概览", path: "/" }, { label: "访客登记", path: "/visitor" }, { label: "门禁通行", path: "/access" }, { label: "样品受理", path: "/sample" }, { label: "委托单位", path: "/client" }, { label: "检测项目", path: "/project" }, { label: "检测任务", path: "/task" }, { label: "检测执行", path: "/execute" }, { label: "检测结果", path: "/result" }, { label: "结果复核", path: "/review" }, { label: "仪器设备", path: "/instrument" }, { label: "校准记录", path: "/calibration" }, { label: "试剂耗材", path: "/reagent" }, { label: "耗材领用", path: "/consume" }, { label: "环境监控", path: "/environment" }, { label: "报告出具", path: "/report" }, { label: "报告变更", path: "/issue" }, { label: "质量控制", path: "/qc" }, { label: "投诉处理", path: "/complaint" }, { label: "样品流转", path: "/stockin" }, { label: "检测结算", path: "/settlement" }]

const groupedOperators = computed(() => {
  const order: OperatorRole[] = ['reception', 'host', 'guard']
  return order.map((role) => ({
    role,
    label: ROLE_LABELS[role],
    items: store.operators.filter((item) => item.role === role),
  })).filter((group) => group.items.length)
})

function onSwitch(operatorId: string) {
  store.setOperator(operatorId)
}

onMounted(async () => {
  try {
    const payload = await fetchJson<{ operators: Operator[] }>('/api/visitor/operators')
    store.hydrate(payload.operators)
  } catch {
    // 目录接口不可用时保持空身份，页面操作会提示先选择身份
  }
})
</script>
