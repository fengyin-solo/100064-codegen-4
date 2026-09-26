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
          当前值班：{{ store.operator }} · {{ store.shiftLabel }}
        </span>
      </header>
      <div class="role-bar">
        <span class="role-label">当前操作角色（权限口径）：</span>
        <label class="role-option" v-for="role in roleOptions" :key="role">
          <input
            type="radio"
            name="operator-role"
            :value="role"
            :checked="store.role === role"
            @change="store.setRole(role)"
          />
          {{ role }}
        </label>
        <label v-if="store.isHost" class="role-option dept-option">
          所属部门
          <select :value="store.department" @change="onDeptChange">
            <option v-for="dept in departments" :key="dept" :value="dept">{{ dept }}</option>
          </select>
        </label>
        <span class="role-hint">{{ roleHint }}</span>
      </div>
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import type { OperatorRole } from '@/stores/session'
import { useSessionStore } from '@/stores/session'
import { fetchJson } from '@/api/client'

const store = useSessionStore()

const navItems = [{ label: "运营概览", path: "/" }, { label: "样品受理", path: "/sample" }, { label: "委托单位", path: "/client" }, { label: "检测项目", path: "/project" }, { label: "检测任务", path: "/task" }, { label: "检测执行", path: "/execute" }, { label: "检测结果", path: "/result" }, { label: "结果复核", path: "/review" }, { label: "仪器设备", path: "/instrument" }, { label: "校准记录", path: "/calibration" }, { label: "试剂耗材", path: "/reagent" }, { label: "耗材领用", path: "/consume" }, { label: "环境监控", path: "/environment" }, { label: "报告出具", path: "/report" }, { label: "报告变更", path: "/issue" }, { label: "质量控制", path: "/qc" }, { label: "投诉处理", path: "/complaint" }, { label: "样品流转", path: "/stockin" }, { label: "检测结算", path: "/settlement" }, { label: "访客登记", path: "/visitor" }, { label: "门禁通行", path: "/access" }]

const roleOptions: OperatorRole[] = ['前台', '被访人', '门禁管理员']
const departments = ref<string[]>(['综合办公室', '检测一部', '检测二部', '质量管理部', '设备保障部'])

onMounted(async () => {
  try {
    const meta = await fetchJson<{ departments: string[] }>('/api/visitor/meta')
    if (meta.departments?.length) departments.value = meta.departments
  } catch {
    // 字典接口不可用时使用内置部门，不影响页面使用
  }
})

function onDeptChange(event: Event) {
  store.setDepartment((event.target as HTMLSelectElement).value)
}

const roleHint = computed(() => {
  if (store.isReception) return '只能进行访客登记'
  if (store.isHost) return `只能审批${store.department}的来访`
  return '可受控发放通行证、核销与查看门禁'
})
</script>
