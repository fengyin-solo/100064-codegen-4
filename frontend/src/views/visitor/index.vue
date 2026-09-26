<template>
  <section class="page" data-module="visitor">
    <header class="page-head">
      <div>
        <h2>访客登记与审批</h2>
        <p class="page-desc">
          前台登记来访人员、受访部门归属与来访事由；被访人只审批本部门来访；
          审批通过后由门禁管理员受控发放通行证。
        </p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/access">前往门禁通行页</RouterLink>
        <button v-if="store.isReception" class="btn primary" type="button" @click="showForm = !showForm">
          {{ showForm ? '收起登记表' : '登记访客' }}
        </button>
      </div>
    </header>

    <p v-if="!store.isReception" class="role-tip warn">
      当前角色为「{{ store.role }}」{{ store.isHost ? `（${store.department}）` : '' }}：
      {{ store.isHost ? '仅可审批本部门来访，登记与发证操作不可用' : '访客登记由前台完成，审批由受访部门完成' }}
    </p>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form v-if="showForm && store.isReception" class="record-form" @submit.prevent="submitRegister">
      <h3>访客登记</h3>
      <div class="form-grid">
        <label class="form-item">
          <span>访客姓名 <em>*</em></span>
          <input v-model="form.访客姓名" placeholder="来访人员姓名" />
        </label>
        <label class="form-item">
          <span>访客单位</span>
          <input v-model="form.访客单位" placeholder="来访人所在单位（可选）" />
        </label>
        <label class="form-item">
          <span>联系电话</span>
          <input v-model="form.联系电话" placeholder="手机号码（可选）" />
        </label>
        <label class="form-item">
          <span>受访部门 <em>*</em></span>
          <select v-model="form.受访部门">
            <option value="" disabled>请选择受访部门</option>
            <option v-for="dept in departments" :key="dept" :value="dept">{{ dept }}</option>
          </select>
        </label>
        <label class="form-item">
          <span>被访人</span>
          <input v-model="form.被访人" placeholder="具体接待人员（可选）" />
        </label>
        <label class="form-item">
          <span>来访日期 <em>*</em></span>
          <input v-model="form.来访日期" type="date" />
        </label>
        <label class="form-item form-wide">
          <span>来访事由 <em>*</em></span>
          <input v-model="form.来访事由" placeholder="例如：设备校准、样品交接、业务洽谈" />
        </label>
      </div>
      <div class="form-actions">
        <button class="btn primary" type="submit">提交登记</button>
        <button class="btn ghost" type="button" @click="resetForm">清空</button>
      </div>
    </form>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>来访日期</span>
        <input v-model="filterDate" type="date" />
      </label>
      <label class="filter-item">
        <span>审批状态</span>
        <select v-model="filterStatus">
          <option value="">全部</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>检索</span>
        <input v-model="filterKeyword" placeholder="访客姓名 / 单位" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th style="width: 220px">审批 / 通行证操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '审批状态'">
              <span :class="['status-tag', statusClass(row.status)]">{{ row.status }}</span>
            </template>
            <template v-else-if="column === '通行证'">
              <span v-if="row.通行证编号">{{ row.通行证编号 }}（{{ row.通行证状态 }}）</span>
              <span v-else class="muted">{{ row.发放说明 }}</span>
            </template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions cell-stack">
            <template v-if="row.status === '待审批' && store.isHost">
              <button class="link" type="button" @click="approve(row, '批准来访')">批准来访</button>
              <button class="link danger" type="button" @click="reject(row)">拒绝来访</button>
            </template>
            <template v-else-if="row.status === '已批准' && store.isGuard">
              <button class="link" type="button" @click="issue(row)">发放通行证</button>
            </template>
            <span v-else class="muted action-hint">{{ actionHint(row) }}</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">{{ emptyText }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条访客登记</span>
      <span v-if="message" :class="messageOk ? 'ok-text' : 'error-text'">{{ message }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { fetchJson, postAction } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | boolean | null>

const store = useSessionStore()
const ENDPOINT = '/api/visitor'

const columns = ['访客编号', '访客姓名', '访客单位', '受访部门', '被访人', '来访事由', '来访日期', '审批状态', '通行证']
const statuses = ['待审批', '已批准', '已拒绝']
const departments = ref<string[]>([])

function today() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const rows = ref<Row[]>([])
const total = ref(0)
const showForm = ref(false)
const message = ref('')
const messageOk = ref(false)
const filterDate = ref(today())
const filterStatus = ref('')
const filterKeyword = ref('')

function blankForm() {
  return {
    访客姓名: '',
    访客单位: '',
    联系电话: '',
    受访部门: '',
    被访人: '',
    来访日期: today(),
    来访事由: '',
  }
}
const form = reactive(blankForm())

const stats = computed(() => {
  const todayRows = rows.value.filter((r) => String(r.来访日期) === today())
  return [
    { label: '本页来访登记', value: rows.value.length },
    { label: '待审批', value: rows.value.filter((r) => r.status === '待审批').length },
    { label: '已批准', value: rows.value.filter((r) => r.status === '已批准').length },
    { label: '通行中通行证', value: todayRows.filter((r) => r.通行证状态 === '通行中').length },
  ]
})

const emptyText = computed(() => {
  if (filterDate.value === today()) return '今天还没有任何来访登记，前台可点击右上角“登记访客”开始录入'
  if (filterStatus.value || filterKeyword.value) return '当前筛选条件下没有来访记录，换个条件再试试'
  return `${filterDate.value} 没有来访登记`
})

function statusClass(status: unknown) {
  if (status === '已批准') return 'tag-ok'
  if (status === '已拒绝') return 'tag-danger'
  return 'tag-pending'
}

function actionHint(row: Row) {
  if (row.status === '待审批') {
    if (store.isHost && row.受访部门 !== store.department) return '非本部门来访，无权审批'
    if (store.isReception) return '等待受访部门审批'
    if (store.isGuard) return '审批通过后才能发证'
  }
  if (row.status === '已批准') return String(row.发放说明 ?? '')
  if (row.status === '已拒绝') return '来访已拒绝'
  return ''
}

function flash(text: string, ok = false) {
  message.value = text
  messageOk.value = ok
}

function resetForm() {
  Object.assign(form, blankForm())
}

function resetFilters() {
  filterDate.value = today()
  filterStatus.value = ''
  filterKeyword.value = ''
  void reload()
}

async function reload() {
  const params = new URLSearchParams()
  if (filterDate.value) params.set('visit_date', filterDate.value)
  if (filterStatus.value) params.set('status', filterStatus.value)
  if (filterKeyword.value) params.set('keyword', filterKeyword.value)
  try {
    const payload = await fetchJson<{ items: Row[]; total: number }>(`${ENDPOINT}?${params.toString()}`)
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    flash(error instanceof Error ? error.message : '访客列表读取失败')
  }
}

async function loadMeta() {
  try {
    const meta = await fetchJson<{ departments: string[] }>('/api/visitor/meta')
    departments.value = meta.departments ?? []
  } catch {
    // 字典加载失败不阻塞，表单使用空选项
  }
}

async function submitRegister() {
  const { status, body } = await postAction(ENDPOINT, { ...form })
  if (status === 403) {
    flash(body.message || '越权操作被拒绝：访客登记仅限前台')
    return
  }
  if (!body.ok) {
    flash(body.message)
    return
  }
  flash(body.message || '访客已登记', true)
  resetForm()
  showForm.value = false
  await reload()
}

async function approve(row: Row, action: string) {
  const opinion = window.prompt(`请输入${action === '拒绝来访' ? '拒绝原因' : '审批意见（可选）'}：`, '')
  if (opinion === null) return
  const values: Record<string, unknown> = { action }
  if (opinion.trim()) values.审批意见 = opinion.trim()
  const { status, body } = await postAction(`${ENDPOINT}/${row.id}/approval`, values)
  if (status === 403) {
    flash(body.message || '越权操作被拒绝')
    return
  }
  flash(body.message, body.ok)
  if (body.ok) await reload()
}

function reject(row: Row) {
  void approve(row, '拒绝来访')
}

async function issue(row: Row) {
  const values: Record<string, unknown> = {}
  const { status, body } = await postAction(`${ENDPOINT}/${row.id}/pass`, values)
  if (status === 403) {
    flash(body.message || '越权操作被拒绝：通行证发放仅限门禁管理员')
    return
  }
  if (!body.ok) {
    flash(body.message)
    return
  }
  flash(body.message, true)
  await reload()
}

onMounted(async () => {
  await Promise.all([loadMeta(), reload()])
})
</script>
