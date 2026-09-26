<template>
  <section class="page" data-module="access">
    <header class="page-head">
      <div>
        <h2>门禁通行</h2>
        <p class="page-desc">
          门禁管理员对已批准来访受控发放通行证；通行证过期即刷不开门，访客离开时核销。
          通行证清单与访客登记页共用同一套可发放状态。
        </p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/visitor">返回访客登记页</RouterLink>
        <button class="btn ghost" type="button" @click="reloadAll">刷新状态</button>
      </div>
    </header>

    <p v-if="!store.isGuard" class="role-tip warn">
      当前角色为「{{ store.role }}」：通行证发放、核销仅限门禁管理员；
      访客审批请切到「被访人」，登记请切到「前台」。
    </p>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <section class="swipe-panel">
      <h3>刷门禁</h3>
      <form class="filter-bar" @submit.prevent="swipe">
        <label class="filter-item grow">
          <span>通行证编号</span>
          <input v-model="swipeCode" placeholder="例如 PASS-0002，闸机读取或手工输入" />
        </label>
        <button class="btn primary" type="submit">刷卡验证</button>
      </form>
      <p v-if="swipeResult" :class="swipeResult.ok ? 'ok-text' : 'error-text'" class="swipe-result">
        {{ swipeResult.ok ? '✅' : '⛔' }} {{ swipeResult.message }}
      </p>
    </section>

    <h3 class="block-title">待发证（已批准且无有效通行证）</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th>访客编号</th><th>访客姓名</th><th>受访部门</th><th>被访人</th><th>来访日期</th><th>可发放状态</th>
          <th style="width: 260px">发放通行证</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in issuableRows" :key="String(row.id)">
          <td>{{ row.访客编号 }}</td>
          <td>{{ row.访客姓名 }}</td>
          <td>{{ row.受访部门 }}</td>
          <td>{{ row.被访人 || '—' }}</td>
          <td>{{ row.来访日期 }}</td>
          <td>{{ row.发放说明 }}</td>
          <td class="row-controls">
            <input v-model="issueForms[Number(row.id)].生效时间" type="datetime-local" title="生效时间" />
            <span class="time-sep">至</span>
            <input v-model="issueForms[Number(row.id)].失效时间" type="datetime-local" title="失效时间" />
            <button class="btn primary small" type="button" @click="issue(row)">发证</button>
          </td>
        </tr>
        <tr v-if="!issuableRows.length">
          <td colspan="7" class="empty-state">没有待发证的已批准来访；审批通过后会出现在这里</td>
        </tr>
      </tbody>
    </table>

    <h3 class="block-title">通行证清单</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th>通行证编号</th><th>访客姓名</th><th>受访部门</th><th>生效时间</th><th>失效时间</th>
          <th>状态</th><th>核销时间</th><th style="width: 160px">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="pass in passes" :key="String(pass.id)">
          <td>{{ pass.通行证编号 }}</td>
          <td>{{ pass.访客姓名 }}</td>
          <td>{{ pass.受访部门 }}</td>
          <td>{{ formatTime(String(pass.生效时间 ?? '')) }}</td>
          <td>{{ formatTime(String(pass.失效时间 ?? '')) }}</td>
          <td><span :class="['status-tag', passStatusClass(pass.通行证状态)]">{{ pass.通行证状态 }}</span></td>
          <td>{{ pass.核销时间 ? formatTime(String(pass.核销时间)) : '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="doSwipe(String(pass.通行证编号))">模拟刷卡</button>
            <button
              v-if="pass.可核销"
              class="link danger"
              type="button"
              :disabled="!store.isGuard"
              :title="store.isGuard ? '访客离开，核销通行证' : '仅门禁管理员可核销'"
              @click="checkout(pass)"
            >
              离开核销
            </button>
            <span v-else class="muted">已核销</span>
          </td>
        </tr>
        <tr v-if="!passes.length">
          <td colspan="8" class="empty-state">还没有发放过通行证</td>
        </tr>
      </tbody>
    </table>

    <h3 class="block-title">最近刷卡记录</h3>
    <table class="data-table">
      <thead>
        <tr><th>刷卡时间</th><th>通行证编号</th><th>访客姓名</th><th>结果</th><th>说明</th></tr>
      </thead>
      <tbody>
        <tr v-for="log in logs" :key="String(log.id)">
          <td>{{ formatTime(log.刷卡时间) }}</td>
          <td>{{ log.通行证编号 }}</td>
          <td>{{ log.访客姓名 }}</td>
          <td>
            <span :class="['status-tag', log.结果 === '放行' ? 'tag-ok' : 'tag-danger']">{{ log.结果 }}</span>
          </td>
          <td>{{ log.原因 }}</td>
        </tr>
        <tr v-if="!logs.length">
          <td colspan="5" class="empty-state">暂无刷卡记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>数据与访客登记页实时一致；从登记页返回或刷新本页都会重新拉取最新状态</span>
      <span v-if="message" :class="messageOk ? 'ok-text' : 'error-text'">{{ message }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { fetchJson, postAction } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type VisitorRow = Record<string, string | number | boolean | null>
type PassRow = Record<string, string | number | boolean | null>
type LogRow = Record<string, string>

const store = useSessionStore()

const visitors = ref<VisitorRow[]>([])
const passes = ref<PassRow[]>([])
const logs = ref<LogRow[]>([])
const swipeCode = ref('')
const swipeResult = ref<{ ok: boolean; message: string } | null>(null)
const message = ref('')
const messageOk = ref(false)
const issueForms = reactive<Record<number, { 生效时间: string; 失效时间: string }>>({})

function today() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function defaultIssueWindow() {
  const day = today()
  const d = new Date()
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return { 生效时间: `${day}T${hh}:${mm}`, 失效时间: `${day}T20:00` }
}

const issuableRows = computed(() => visitors.value.filter((row) => row.可发放通行证))

const stats = computed(() => [
  { label: '待发证来访', value: issuableRows.value.length },
  { label: '通行中', value: passes.value.filter((p) => p.通行证状态 === '通行中').length },
  { label: '已过期未核销', value: passes.value.filter((p) => p.通行证状态 === '已过期').length },
  { label: '已核销', value: passes.value.filter((p) => p.通行证状态 === '已核销').length },
])

function formatTime(value: unknown) {
  const text = String(value ?? '')
  return text ? text.replace('T', ' ') : '—'
}

function passStatusClass(status: unknown) {
  if (status === '通行中') return 'tag-ok'
  if (status === '已核销') return 'tag-muted'
  return 'tag-danger'
}

function flash(text: string, ok = false) {
  message.value = text
  messageOk.value = ok
}

function ensureIssueForm(row: VisitorRow) {
  const id = Number(row.id)
  if (!issueForms[id]) issueForms[id] = defaultIssueWindow()
}

async function loadVisitors() {
  // 与访客登记页同一个接口、同一个默认日期口径，保证可发放状态一致。
  const payload = await fetchJson<{ items: VisitorRow[] }>(`/api/visitor?visit_date=all&size=200`)
  visitors.value = payload.items ?? []
  visitors.value.forEach(ensureIssueForm)
}

async function loadPasses() {
  const payload = await fetchJson<{ items: PassRow[] }>('/api/visitor/passes')
  passes.value = payload.items ?? []
}

async function loadLogs() {
  const payload = await fetchJson<{ items: LogRow[] }>('/api/visitor/access-logs?limit=20')
  logs.value = payload.items ?? []
}

async function reloadAll() {
  message.value = ''
  try {
    await Promise.all([loadVisitors(), loadPasses(), loadLogs()])
  } catch (error) {
    flash(error instanceof Error ? error.message : '门禁数据读取失败')
  }
}

async function issue(row: VisitorRow) {
  swipeResult.value = null
  if (!store.isGuard) {
    flash('越权操作被拒绝：通行证发放仅限门禁管理员')
    return
  }
  const id = Number(row.id)
  ensureIssueForm(row)
  const win = issueForms[id]
  const { status, body } = await postAction(`/api/visitor/${id}/pass`, {
    生效时间: win.生效时间,
    失效时间: win.失效时间,
  })
  if (status === 403) {
    flash(body.message || '越权操作被拒绝')
    return
  }
  flash(body.message, body.ok)
  if (body.ok) {
    swipeCode.value = String(body.entry?.通行证编号 ?? '')
    await reloadAll()
  }
}

async function doSwipe(code: string) {
  swipeCode.value = code
  await swipe()
}

async function swipe() {
  const code = swipeCode.value.trim()
  if (!code) {
    swipeResult.value = { ok: false, message: '请先输入通行证编号' }
    return
  }
  const { body } = await postAction(`/api/visitor/pass/${encodeURIComponent(code)}/swipe`, {})
  swipeResult.value = { ok: body.ok, message: body.message }
  await loadLogs()
  await loadPasses()
}

async function checkout(pass: PassRow) {
  if (!store.isGuard) {
    flash('越权操作被拒绝：通行证核销仅限门禁管理员')
    return
  }
  const { status, body } = await postAction(`/api/visitor/pass/${pass.id}/checkout`, {})
  if (status === 403) {
    flash(body.message || '越权操作被拒绝')
    return
  }
  // 重复核销后端只算一次，message 里会明确提示“只计一次”。
  flash(body.message, body.ok)
  await reloadAll()
}

onMounted(reloadAll)
</script>
