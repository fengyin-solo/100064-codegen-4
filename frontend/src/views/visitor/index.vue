<template>
  <section class="page" data-module="visitor">
    <header class="page-head">
      <div>
        <h2>访客登记与来访审批</h2>
        <p class="page-desc">登记来访人员、受访部门归属与来访事由，提交被访人按部门审批；批准后由门禁管理员在「门禁通行」发放通行证。</p>
      </div>
      <div class="page-actions">
        <button v-if="store.isReception" class="btn primary" type="button" @click="openCreate">登记访客</button>
        <RouterLink class="btn" to="/access">前往门禁通行</RouterLink>
      </div>
    </header>

    <p class="role-hint" :class="`role-${store.operator?.role ?? 'none'}`">
      当前身份：<strong>{{ identityText }}</strong> · {{ permissionText }}
    </p>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>来访日期</span>
        <input v-model="filters.visit_date" type="date" />
      </label>
      <label class="filter-item">
        <span>受访部门</span>
        <select v-model="filters.dept">
          <option value="">全部部门</option>
          <option v-for="dept in departments" :key="dept" :value="dept">{{ dept }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>审批状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>访客检索</span>
        <input v-model="filters.keyword" placeholder="按姓名 / 单位 / 编号检索" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>状态</th>
          <th>可执行操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td><span class="badge" :class="badgeClass(String(row.status))">{{ row.status }}</span></td>
          <td class="row-actions">
            <template v-if="canApprove(row)">
              <button class="link" type="button" @click="openApprove(row, true)">批准来访</button>
              <button class="link danger" type="button" @click="openApprove(row, false)">驳回来访</button>
            </template>
            <span v-else-if="row.status === '待审批'" class="action-muted">
              {{ store.isHost ? '非本部门来访，无权审批' : '等待被访人审批' }}
            </span>
            <span v-else-if="row.status === '已批准'" class="action-muted">已批准，待门禁发证</span>
            <span v-else class="action-muted">—</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">
            {{ emptyText }}
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条访客登记（{{ filters.visit_date || '全部日期' }}）</span>
      <span v-if="successMessage" class="success-text">{{ successMessage }}</span>
      <span v-else-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 访客登记表单 -->
    <div v-if="creating" class="modal-mask" @click.self="closeCreate">
      <div class="modal">
        <h3>访客登记</h3>
        <p class="modal-desc">请填写来访人员与受访信息，提交后进入被访人审批。</p>
        <form class="modal-form" @submit.prevent="submitCreate">
          <label v-for="field in createFields" :key="field.key" class="modal-field" :class="{ required: field.required }">
            <span>{{ field.label }}</span>
            <select v-if="field.key === '受访部门'" v-model="form[field.key]" required @change="onDeptChange">
              <option value="" disabled>请选择受访部门</option>
              <option v-for="dept in departments" :key="dept" :value="dept">{{ dept }}</option>
            </select>
            <select v-else-if="field.key === '被访人'" v-model="form[field.key]" required>
              <option value="" disabled>请先选择受访部门</option>
              <option v-if="selectedDept" :value="selectedDept.host">{{ selectedDept.host }}（{{ selectedDept.name }}）</option>
            </select>
            <input
              v-else
              v-model="form[field.key]"
              :type="field.type ?? 'text'"
              :required="field.required"
              :placeholder="field.placeholder ?? `请填写${field.label}`"
            />
          </label>
          <p v-if="formError" class="error-text modal-error">{{ formError }}</p>
          <div class="modal-actions">
            <button class="btn" type="button" @click="closeCreate">取消</button>
            <button class="btn primary" type="submit">提交登记</button>
          </div>
        </form>
      </div>
    </div>

    <!-- 审批意见 -->
    <div v-if="approving" class="modal-mask" @click.self="approving = null">
      <div class="modal modal-sm">
        <h3>{{ approving.approved ? '批准来访' : '驳回来访' }}</h3>
        <p class="modal-desc">
          {{ approving.row['访客姓名'] }} 来访「{{ approving.row['受访部门'] }}」，事由：{{ approving.row['来访事由'] }}
        </p>
        <form class="modal-form" @submit.prevent="submitApprove">
          <label class="modal-field">
            <span>审批意见</span>
            <textarea v-model="approveComment" rows="3" :placeholder="approving.approved ? '可留空，默认「同意来访」' : '请说明驳回原因'"></textarea>
          </label>
          <p v-if="formError" class="error-text modal-error">{{ formError }}</p>
          <div class="modal-actions">
            <button class="btn" type="button" @click="approving = null">取消</button>
            <button class="btn primary" type="submit">确认{{ approving.approved ? '批准' : '驳回' }}</button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { fetchJson, postAction, request } from '@/api/client'
import { ROLE_LABELS, useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>

const store = useSessionStore()

const ENDPOINT = '/api/visitor'
const columns = ['来访编号', '访客姓名', '来访单位', '联系方式', '受访部门', '被访人', '来访事由', '来访日期', '到访时间', '登记人', '审批人']
const statuses = ['待审批', '已批准', '已驳回', '已核销']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const departments = ref<string[]>([])
const departmentHosts = ref<{ name: string; host: string }[]>([])

function today() {
  return new Date().toISOString().slice(0, 10)
}

const filters = reactive({ visit_date: today(), dept: '', status: '', keyword: '' })

const stats = computed(() => [
  { label: '当天来访登记', value: dayRows.value.length },
  { label: '待本部门审批', value: pendingMine.value.length },
  { label: '已批准待发证', value: approvedToday.value },
  { label: '已驳回', value: dayRows.value.filter((row) => row.status === '已驳回').length },
])

const dayRows = ref<Row[]>([])
const pendingMine = computed(() =>
  dayRows.value.filter((row) => row.status === '待审批' && row['受访部门'] === store.operator?.department),
)
const approvedToday = ref(0)

const identityText = computed(() =>
  store.operator ? `${store.operator.name}（${ROLE_LABELS[store.operator.role]} · ${store.operator.department}）` : '未选择身份',
)
const permissionText = computed(() => {
  if (store.isReception) return '只能进行访客登记，不能审批或发放通行证'
  if (store.isHost) return '只能审批自己部门的来访，跨部门来访会被拒绝'
  if (store.isGuard) return '访客登记与审批不可操作，请在门禁通行页发放与核销通行证'
  return '请先在右上角选择操作身份'
})

const emptyText = computed(() => {
  const hasFilter = filters.dept || filters.status || filters.keyword
  if (hasFilter) return '当前筛选条件下没有访客登记，可调整条件后再查'
  return filters.visit_date === today()
    ? '今天还没有任何访客登记，前台完成登记后，来访会在这里显示并提交被访人审批。'
    : `${filters.visit_date || '当天'} 没有访客登记记录`
})

type CreateField = {
  key: string
  label: string
  required: boolean
  type?: string
  placeholder?: string
}

const createFields: CreateField[] = [
  { key: '访客姓名', label: '访客姓名', required: true },
  { key: '来访单位', label: '来访单位', required: true },
  { key: '联系方式', label: '联系方式', required: false, placeholder: '选填，手机号或座机' },
  { key: '证件号', label: '证件号', required: false, placeholder: '选填，身份证/证件后四位' },
  { key: '受访部门', label: '受访部门', required: true, type: 'select' },
  { key: '被访人', label: '被访人', required: true, type: 'select' },
  { key: '来访事由', label: '来访事由', required: true, placeholder: '例如：送检样品、设备维保、参观交流' },
  { key: '来访日期', label: '来访日期', required: true, type: 'date' },
  { key: '到访时间', label: '到访时间', required: true, type: 'time' },
]

const creating = ref(false)
const formError = ref('')
const form = reactive<Record<string, string>>({})
const selectedDept = computed(() => departmentHosts.value.find((item) => item.name === form['受访部门']))

function onDeptChange() {
  // 部门与被访人是绑定关系，换部门要清空之前选的被访人
  form['被访人'] = ''
}

const approving = ref<{ row: Row; approved: boolean } | null>(null)
const approveComment = ref('')

function badgeClass(status: string) {
  return {
    待审批: 'badge-pending',
    已批准: 'badge-ok',
    已驳回: 'badge-bad',
    已核销: 'badge-done',
  }[status] ?? ''
}

function canApprove(row: Row) {
  return store.isHost && row.status === '待审批' && row['受访部门'] === store.operator?.department
}

function resetFilters() {
  filters.visit_date = today()
  filters.dept = ''
  filters.status = ''
  filters.keyword = ''
  void reload()
}

function openCreate() {
  Object.keys(form).forEach((key) => delete form[key])
  form['来访日期'] = today()
  form['受访部门'] = ''
  form['被访人'] = ''
  formError.value = ''
  creating.value = true
}

function closeCreate() {
  creating.value = false
}

async function submitCreate() {
  formError.value = ''
  try {
    const payload = (await postAction(ENDPOINT, { ...form })) as { message: string }
    errorMessage.value = ''
    creating.value = false
    await reload()
    flashMessage(payload.message || '访客登记成功')
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '访客登记失败'
  }
}

function openApprove(row: Row, approved: boolean) {
  approving.value = { row, approved }
  approveComment.value = ''
  formError.value = ''
}

async function submitApprove() {
  if (!approving.value) return
  const target = approving.value
  if (!target.approved && !approveComment.value.trim()) {
    formError.value = '驳回来访必须填写审批意见，说明驳回原因'
    return
  }
  formError.value = ''
  try {
    const payload = (await postAction(`${ENDPOINT}/${target.row.id}/actions`, {
      action: target.approved ? '批准来访' : '驳回来访',
      comment: approveComment.value.trim(),
    })) as { message: string }
    approving.value = null
    await reload()
    flashMessage(payload.message)
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '审批未生效'
  }
}

let flashTimer: number | undefined
function flashMessage(text: string) {
  errorMessage.value = ''
  successMessage.value = text
  window.clearTimeout(flashTimer)
  flashTimer = window.setTimeout(() => (successMessage.value = ''), 3000)
}
const successMessage = ref('')

async function loadDirectory() {
  try {
    const payload = await fetchJson<{
      departments: string[]
      departmentHosts: { name: string; host: string }[]
    }>('/api/visitor/operators')
    departments.value = payload.departments
    departmentHosts.value = payload.departmentHosts
  } catch {
    departments.value = []
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value) query.set(key, value)
  })
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) throw new Error('访客列表读取失败')
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '访客列表读取失败'
  }
  // 统计始终以「当天全量」为准，不受筛选影响
  try {
    const response = await request(`${ENDPOINT}?visit_date=${today()}&size=200`)
    const payload = await response.json()
    dayRows.value = payload.items ?? []
    approvedToday.value = dayRows.value.filter((row: Row) => row.status === '已批准').length
  } catch {
    dayRows.value = []
  }
}

onMounted(async () => {
  await loadDirectory()
  await reload()
})
</script>
