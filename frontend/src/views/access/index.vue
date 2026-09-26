<template>
  <section class="page" data-module="access">
    <header class="page-head">
      <div>
        <h2>访客门禁通行</h2>
        <p class="page-desc">按已批准的来访受控发放通行证；通行证超过有效期自动失效，访客离开时核销，重复核销只计一次。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/visitor">返回访客登记</RouterLink>
        <button class="btn" type="button" @click="reloadAll()">刷新状态</button>
      </div>
    </header>

    <p class="role-hint" :class="`role-${store.operator?.role ?? 'none'}`">
      当前身份：<strong>{{ identityText }}</strong> · {{ permissionText }}
    </p>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="item.danger ? 'stat-danger' : ''">{{ item.value }}</strong>
      </article>
    </div>

    <!-- 一、可发放通行证的来访 -->
    <h3 class="section-title">待发放通行证的来访（{{ todayLabel }} 已批准）</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in issuableColumns" :key="column">{{ column }}</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in issuableRows" :key="String(row.id)">
          <td v-for="column in issuableColumns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button v-if="store.isGuard" class="link" type="button" @click="openIssue(row)">发放通行证</button>
            <span v-else-if="row.status === '已批准'" class="action-muted">仅门禁管理员可发放</span>
          </td>
        </tr>
        <tr v-if="!issuableRows.length">
          <td :colspan="issuableColumns.length + 1" class="empty-state">
            今天没有已批准且待发放通行证的来访；访客批准通过后会出现在这里。
          </td>
        </tr>
      </tbody>
    </table>

    <!-- 二、门禁操作：刷卡 + 核销 -->
    <div class="access-panels">
      <div class="access-panel">
        <h3 class="section-title">门禁刷卡</h3>
        <form class="inline-form" @submit.prevent="submitSwipe">
          <input v-model="swipeNo" placeholder="输入通行证号，如 PASS-0001" :disabled="!store.isGuard" />
          <button class="btn primary" type="submit" :disabled="!store.isGuard || busy">刷门禁</button>
        </form>
        <p v-if="!store.isGuard" class="action-muted">刷卡判定由门禁管理员操作；过期、未生效或已核销的通行证会被拒绝。</p>
        <div v-if="swipeResult" class="gate-result" :class="swipeResult.allowed ? 'gate-allow' : 'gate-deny'">
          <strong>{{ swipeResult.allowed ? '✅ 门禁放行' : '⛔ 门禁拒绝' }}</strong>
          <span>{{ swipeResult.message }}</span>
        </div>
      </div>
      <div class="access-panel">
        <h3 class="section-title">离开核销</h3>
        <form class="inline-form" @submit.prevent="submitCheckout">
          <input v-model="checkoutNo" placeholder="输入要核销的通行证号" :disabled="!store.isGuard" />
          <button class="btn primary" type="submit" :disabled="!store.isGuard || busy">核销离开</button>
        </form>
        <p v-if="!store.isGuard" class="action-muted">通行证核销仅限门禁管理员；同一张通行证重复核销只算一次。</p>
        <div v-if="checkoutResult" class="gate-result gate-info">
          <strong>核销结果</strong>
          <span>{{ checkoutResult }}</span>
        </div>
      </div>
    </div>

    <!-- 三、通行证台账 -->
    <h3 class="section-title">通行证台账</h3>
    <form class="filter-bar" @submit.prevent="loadPasses">
      <label class="filter-item">
        <span>通行证状态</span>
        <select v-model="passFilter.status">
          <option value="">全部</option>
          <option v-for="status in passStatuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>检索</span>
        <input v-model="passFilter.keyword" placeholder="通行证号 / 访客姓名" />
      </label>
      <button class="btn" type="submit">查询</button>
    </form>
    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in passColumns" :key="column">{{ column }}</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in passRows" :key="String(row.id)">
          <td v-for="column in passColumns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <template v-if="store.isGuard">
              <button class="link" type="button" @click="quickSwipe(String(row['通行证号']))">刷门禁</button>
              <button
                class="link"
                :class="{ danger: row['通行证状态'] !== '已核销' }"
                type="button"
                @click="quickCheckout(String(row['通行证号']))"
              >
                {{ row['通行证状态'] === '已核销' ? '再次核销' : '核销离开' }}
              </button>
            </template>
            <span v-else class="action-muted">仅门禁管理员操作</span>
          </td>
        </tr>
        <tr v-if="!passRows.length">
          <td :colspan="passColumns.length + 1" class="empty-state">暂无通行证记录，批准来访后可在此发放。</td>
        </tr>
      </tbody>
    </table>

    <!-- 四、刷卡/核销记录 -->
    <h3 class="section-title">门禁通行记录（最近 {{ logRows.length }} 条）</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in logColumns" :key="column">{{ column }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in logRows" :key="String(row.id)">
          <td v-for="column in logColumns" :key="column">{{ row[column] ?? '—' }}</td>
        </tr>
        <tr v-if="!logRows.length">
          <td :colspan="logColumns.length" class="empty-state">今天还没有任何刷卡或核销记录。</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>通行证状态按当前时刻实时判定，刷新或返回页面后与门禁结果保持一致</span>
      <span v-if="noticeMessage" class="success-text">{{ noticeMessage }}</span>
      <span v-else-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 发放通行证弹窗 -->
    <div v-if="issuing" class="modal-mask" @click.self="issuing = null">
      <div class="modal">
        <h3>发放访客通行证</h3>
        <p class="modal-desc">
          {{ issuing.visit['访客姓名'] }} · {{ issuing.visit['来访编号'] }} · 受访部门{{ issuing.visit['受访部门'] }}
        </p>
        <form class="modal-form" @submit.prevent="submitIssue">
          <label class="modal-field">
            <span>门禁点</span>
            <select v-model="issueForm.point">
              <option value="东门访客通道">东门访客通道</option>
              <option value="西门访客通道">西门访客通道</option>
              <option value="样品交接区闸机">样品交接区闸机</option>
            </select>
          </label>
          <label class="modal-field">
            <span>有效开始</span>
            <input v-model="issueForm.valid_from" type="datetime-local" required />
          </label>
          <label class="modal-field">
            <span>有效截止</span>
            <input v-model="issueForm.valid_until" type="datetime-local" required />
          </label>
          <p class="modal-tip">通行证仅限来访当日有效，不允许跨日发放；截止后再刷门禁将被拒绝。</p>
          <p v-if="formError" class="error-text modal-error">{{ formError }}</p>
          <div class="modal-actions">
            <button class="btn" type="button" @click="issuing = null">取消</button>
            <button class="btn primary" type="submit">确认发放</button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { postAction, request } from '@/api/client'
import { ROLE_LABELS, useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | null>

const store = useSessionStore()

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}
function toLocalInput(date: Date) {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}
// 后端接收 YYYY-MM-DD HH:MM
function toApiTime(value: string) {
  return value.replace('T', ' ')
}

const issuableColumns = ['来访编号', '访客姓名', '来访单位', '受访部门', '被访人', '来访事由', '到访时间']
const passColumns = ['通行证号', '访客姓名', '受访部门', '门禁点', '发证时间', '有效开始', '有效截止', '通行证状态', '核销时间']
const logColumns = ['刷卡时间', '通行证号', '访客姓名', '门禁点', '结果', '说明']
const passStatuses = ['通行中', '未生效', '已过期', '已核销']

const issuableRows = ref<Row[]>([])
const passRows = ref<Row[]>([])
const allPassRows = ref<Row[]>([])
const logRows = ref<Row[]>([])
const errorMessage = ref('')
const noticeMessage = ref('')
const busy = ref(false)
const todayLabel = todayStr()

const passFilter = reactive({ status: '', keyword: '' })

const stats = computed(() => [
  { label: '通行中', value: allPassRows.value.filter((row) => row['通行证状态'] === '通行中').length, danger: false },
  { label: '已过期未核销', value: allPassRows.value.filter((row) => row['通行证状态'] === '已过期').length, danger: true },
  { label: '已核销', value: allPassRows.value.filter((row) => row['通行证状态'] === '已核销').length, danger: false },
  { label: '可发放来访', value: issuableRows.value.length, danger: false },
])

const identityText = computed(() =>
  store.operator ? `${store.operator.name}（${ROLE_LABELS[store.operator.role]} · ${store.operator.department}）` : '未选择身份',
)
const permissionText = computed(() => {
  if (store.isGuard) return '可受控发放通行证、刷门禁与离开核销；非已批准/跨日有效期/重复发放都会被拒绝'
  if (store.isReception) return '只能查看门禁信息；发放与核销请切换门禁管理员身份'
  if (store.isHost) return '只能查看门禁信息，审批请在访客登记页操作'
  return '请先在右上角选择操作身份'
})

// 发放弹窗
const issuing = ref<{ visit: Row } | null>(null)
const issueForm = reactive({ point: '东门访客通道', valid_from: '', valid_until: '' })
const formError = ref('')

// 刷卡 / 核销结果
const swipeNo = ref('')
const swipeResult = ref<{ allowed: boolean; message: string } | null>(null)
const checkoutNo = ref('')
const checkoutResult = ref('')

function openIssue(visit: Row) {
  const start = new Date()
  start.setMinutes(start.getMinutes() + 1, 0, 0)
  const end = new Date(start.getTime() + 4 * 60 * 60 * 1000)
  // 默认不超过当日 23:59
  const endOfDay = new Date(start)
  endOfDay.setHours(23, 59, 0, 0)
  const cappedEnd = end > endOfDay ? endOfDay : end
  issueForm.point = '东门访客通道'
  issueForm.valid_from = toLocalInput(start)
  issueForm.valid_until = toLocalInput(cappedEnd)
  formError.value = ''
  issuing.value = { visit }
}

async function submitIssue() {
  if (!issuing.value || !issueForm.valid_from || !issueForm.valid_until) {
    formError.value = '请完整选择有效期起止时间'
    return
  }
  if (toApiTime(issueForm.valid_until) <= toApiTime(issueForm.valid_from)) {
    formError.value = '有效开始必须早于有效截止'
    return
  }
  formError.value = ''
  busy.value = true
  try {
    const payload = (await postAction('/api/access/passes', {
      visit_id: issuing.value.visit.id,
      point: issueForm.point,
      valid_from: toApiTime(issueForm.valid_from),
      valid_until: toApiTime(issueForm.valid_until),
    })) as { message: string }
    issuing.value = null
    errorMessage.value = ''
    await reloadAll(payload.message)
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '通行证发放失败'
  } finally {
    busy.value = false
  }
}

async function submitSwipe() {
  const code = swipeNo.value.trim().toUpperCase()
  if (!code) return
  swipeResult.value = null
  busy.value = true
  try {
    const response = await request('/api/access/swipe', {
      method: 'POST',
      body: JSON.stringify({ values: { pass_no: code } }),
    })
    const payload = await response.json()
    if (!response.ok) throw new Error(payload.detail || '刷卡失败')
    swipeResult.value = { allowed: Boolean(payload.allowed), message: payload.message }
    swipeNo.value = ''
    await Promise.all([loadPasses(), loadLogs()])
  } catch (error) {
    swipeResult.value = { allowed: false, message: error instanceof Error ? error.message : '刷卡请求失败' }
  } finally {
    busy.value = false
  }
}

function quickSwipe(code: string) {
  swipeNo.value = code
  void submitSwipe()
}

async function submitCheckout() {
  const code = checkoutNo.value.trim().toUpperCase()
  if (!code) return
  checkoutResult.value = ''
  busy.value = true
  try {
    const payload = (await postAction('/api/access/checkout', { pass_no: code })) as { message: string }
    checkoutResult.value = payload.message
    checkoutNo.value = ''
    await reloadAll()
  } catch (error) {
    checkoutResult.value = error instanceof Error ? error.message : '核销失败'
  } finally {
    busy.value = false
  }
}

async function quickCheckout(code: string) {
  checkoutNo.value = code
  await submitCheckout()
}

async function loadIssuable() {
  try {
    const response = await request(`/api/access/issuable?visit_date=${todayLabel}`)
    const payload = await response.json()
    issuableRows.value = payload.items ?? []
  } catch {
    issuableRows.value = []
  }
}

async function loadPasses() {
  errorMessage.value = ''
  // 统计用：先取未过滤的全量状态（分页 200 足够演示）
  try {
    const responseAll = await request('/api/access/passes?size=200')
    const payloadAll = await responseAll.json()
    allPassRows.value = payloadAll.items ?? []
  } catch {
    allPassRows.value = []
  }
  // 表格用：按当前过滤条件
  const query = new URLSearchParams()
  if (passFilter.status) query.set('status', passFilter.status)
  if (passFilter.keyword) query.set('keyword', passFilter.keyword)
  try {
    const response = await request(`/api/access/passes?${query.toString()}`)
    if (!response.ok) throw new Error('通行证台账读取失败')
    const payload = await response.json()
    passRows.value = payload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '通行证台账读取失败'
  }
}

async function loadLogs() {
  try {
    const response = await request('/api/access/logs?size=20')
    const payload = await response.json()
    logRows.value = payload.items ?? []
  } catch {
    logRows.value = []
  }
}

async function reloadAll(notice?: string) {
  await Promise.all([loadIssuable(), loadPasses(), loadLogs()])
  if (notice) {
    noticeMessage.value = notice
    window.setTimeout(() => (noticeMessage.value = ''), 4000)
  }
}

onMounted(() => {
  void reloadAll()
})
</script>
