<template>
  <Login v-if="!authed" @logged-in="onLoggedIn" />
  <div v-else class="layout">
    <header class="topbar card">
      <div class="brand">
        <span class="logo">🧾</span>
        <div>
          <h1>发票解析系统</h1>
          <p>上传发票 → 自动解析 → 按时间排序 → 导出 Bills + Expenses report（原格式）</p>
        </div>
      </div>
      <div class="tabs">
        <button :class="{ tabbtn: true, active: page === 'invoice' }" @click="page = 'invoice'">发票解析</button>
        <button :class="{ tabbtn: true, active: page === 'translate' }" @click="page = 'translate'">文档翻译</button>
      </div>
      <div class="actions">
        <span class="user" :title="username">👤 {{ username }}</span>
        <button @click="pwOpen = true">修改密码</button>
        <button @click="logout">退出</button>
        <button class="danger" @click="clearAll" :disabled="!invoices.length">清空</button>
        <button class="primary" @click="exportXlsx" :disabled="!invoices.length || exporting">
          {{ exporting ? '导出中…' : '导出 Excel' }}
        </button>
      </div>
    </header>

    <div v-show="page === 'invoice'">
    <!-- 上传区 -->
    <div
      class="dropzone card"
      :class="{ drag }"
      @dragover.prevent="drag = true"
      @dragleave="drag = false"
      @drop.prevent="onDrop"
      @click="fileInput?.click()"
    >
      <input
        ref="fileInput"
        type="file"
        multiple
        accept=".pdf,.ofd,.png,.jpg,.jpeg,.webp,.bmp"
        style="display: none"
        @change="e => onPick((e.target as HTMLInputElement).files)"
      />
      <div v-if="!uploading" class="dz-inner">
        <div class="dz-icon">📄</div>
        <b>拖拽发票到此处，或点击选择文件</b>
        <p>支持 PDF / OFD / 图片，可一次选多张；解析后自动按时间排序并编号</p>
      </div>
      <div v-else class="dz-inner">
        <div class="spinner"></div>
        <b>正在解析 {{ uploading }} 张发票…（首次解析含模型加载，稍慢）</b>
      </div>
    </div>

    <!-- Tracker 基准 -->
    <div class="tracker-bar card">
      <span class="tb-label">📘 Tracker 基准</span>
      <template v-if="tracker.loaded">
        <b class="tb-name">{{ tracker.filename }}</b>
        <span class="badge gray">{{ tracker.sheets.length }} 个 sheet</span>
        <span class="tb-hint">导出时在其副本上追加 Expenses report / Bills，原表保留</span>
        <button class="tb-btn" @click="removeTracker">移除</button>
      </template>
      <template v-else>
        <button class="tb-btn" @click="trackerInput?.click()">上传 Tracker list.xlsx</button>
        <span class="tb-hint">不上传时导出仅含 Expenses report + Bills 两个 sheet</span>
        <input
          ref="trackerInput"
          type="file"
          accept=".xlsx"
          style="display: none"
          @change="e => onPickTracker((e.target as HTMLInputElement).files)"
        />
      </template>
    </div>

    <!-- Expenses report -->
    <section class="section card">
      <h2>
        Expenses report
        <span class="tag">路程表 · 按时间排序 · 表头与原表一致</span>
        <span class="badge">{{ expenses.length }} 行</span>
        <span class="badge gray" v-if="travelTotal !== null">合计 ¥{{ travelTotal.toFixed(2) }}</span>
        <button class="add" @click="manualOpen = !manualOpen">＋ 添加无发票行程</button>
      </h2>

      <div v-if="manualOpen" class="manual card">
        <label>日期 <input type="date" v-model="manual.date" /></label>
        <label>项目 <input v-model="manual.item" placeholder="滴滴打车/高铁/火车…" /></label>
        <label>路程 <input v-model="manual.location" placeholder="A至B" /></label>
        <label>金额 <input type="number" step="0.01" v-model.number="manual.amount" /></label>
        <label>备注 <input v-model="manual.note" placeholder="（工厂已付）" /></label>
        <div>
          <button class="primary" @click="addManual">保存</button>
          <button @click="manualOpen = false">取消</button>
        </div>
      </div>

      <div v-if="!expenses.length" class="empty">暂无路程记录，上传交通类发票（打车/火车/动车等）会自动出现在这里</div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width: 120px">Date:</th>
              <th style="width: 110px">Item:</th>
              <th>Location:</th>
              <th style="width: 110px">Amt (RMB):</th>
              <th style="width: 90px">HK$</th>
              <th style="width: 110px">Bill No.</th>
              <th style="width: 46px"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="inv in expenses" :key="inv.id" :class="{ nobill: inv.no_bill }">
              <td><input type="date" :value="inv.date" @change="upd(inv, { date: val($event) })" /></td>
              <td><input :value="inv.item" @change="upd(inv, { item: val($event) })" /></td>
              <td><input :value="inv.location" @change="upd(inv, { location: val($event) })" /></td>
              <td><input type="number" step="0.01" :value="inv.amount ?? ''" @change="upd(inv, { amount: num($event) })" /></td>
              <td><input :value="inv.hkd" placeholder="—" @change="upd(inv, { hkd: val($event) })" /></td>
              <td class="billno">
                <span v-if="!inv.no_bill" class="badge">{{ billNoOf(invoices, inv) }}#</span>
                <input v-else :value="inv.note" @change="upd(inv, { note: val($event) })" title="无发票备注" />
              </td>
              <td><button class="danger del" @click="del(inv)">✕</button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Bills -->
    <section class="section card">
      <h2>
        Bills
        <span class="tag">全部发票 · 按时间顺序编号贴图</span>
        <span class="badge">{{ bills.length }} 张</span>
      </h2>
      <div v-if="!bills.length" class="empty">还没有发票，先上传几张试试</div>
      <div v-else class="grid">
        <div v-for="inv in bills" :key="inv.id" class="bill card">
          <div class="bill-no" v-if="billNoOf(invoices, inv)">{{ billNoOf(invoices, inv) }}#</div>
          <div class="thumb" @click="preview = inv">
            <img v-if="thumbUrl(inv)" :src="thumbUrl(inv)!" loading="lazy" />
            <div v-else class="no-thumb">{{ inv.file_type.toUpperCase() }}<br />无法预览</div>
          </div>
          <div class="meta">
            <div class="row1">
              <span class="name" :title="inv.filename">{{ inv.filename }}</span>
              <span class="amt">{{ inv.amount !== null ? '¥' + inv.amount.toFixed(2) : '—' }}</span>
            </div>
            <div class="row2">
              <input type="date" :value="inv.date" @change="upd(inv, { date: val($event) })" />
              <input type="time" :value="inv.time" @change="upd(inv, { time: val($event) })" />
            </div>
            <div class="row3">
              <input :value="inv.item" placeholder="项目" @change="upd(inv, { item: val($event) })" />
              <button
                class="cat"
                :class="{ travel: inv.category === 'travel' }"
                :title="inv.category === 'travel' ? '点击改为不进路程表' : '点击改为进路程表'"
                @click="upd(inv, { category: inv.category === 'travel' ? 'other' : 'travel' })"
              >{{ inv.category === 'travel' ? '→ 路程' : '→ Bills' }}</button>
            </div>
            <div class="row3">
              <input class="loc" :value="inv.location" placeholder="路程（打车票留空，人工补充）" @change="upd(inv, { location: val($event) })" />
            </div>
            <div class="warn" v-if="inv.parse_msg">⚠ {{ inv.parse_msg }}</div>
            <button class="danger del" @click="del(inv)">删除</button>
          </div>
        </div>
      </div>
    </section>

    </div><!-- /page:invoice -->

    <Translate v-show="page === 'translate'" @toast="showToast" />

    <!-- 修改密码 -->
    <teleport to="body">
      <div v-if="pwOpen" class="modal-mask" @click.self="pwOpen = false">
        <form class="modal card" @submit.prevent="submitPw">
          <h3>修改密码</h3>
          <label>原密码
            <input v-model="pw.old" type="password" autocomplete="current-password" />
          </label>
          <label>新密码（至少 8 位，含字母和数字）
            <input v-model="pw.p1" type="password" autocomplete="new-password" />
          </label>
          <label>确认新密码
            <input v-model="pw.p2" type="password" autocomplete="new-password" />
          </label>
          <div v-if="pwErr" class="modal-err">{{ pwErr }}</div>
          <div class="modal-btns">
            <button type="button" @click="pwOpen = false">取消</button>
            <button class="primary" type="submit" :disabled="pwLoading">
              {{ pwLoading ? '保存中…' : '确认修改' }}
            </button>
          </div>
        </form>
      </div>
    </teleport>

    <!-- 预览 -->
    <teleport to="body">
      <div v-if="preview" class="lightbox" @click="preview = null">
        <img v-if="thumbUrl(preview)" :src="thumbUrl(preview)!" />
        <iframe v-else-if="preview.file_type === 'pdf'" :src="fileUrl(preview)!" />
        <div v-else class="no-thumb big">{{ preview.file_type.toUpperCase() }} 暂不支持预览</div>
        <p>点击任意处关闭 · <a :href="fileUrl(preview) || '#'" target="_blank">打开原文件</a></p>
      </div>
    </teleport>

    <footer class="foot">
      共 {{ invoices.length }} 条记录 · Bills {{ bills.length }} 张 · Expenses report {{ expenses.length }} 行
    </footer>
    <div v-if="toast" class="toast">{{ toast }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, ApiError } from './api'
import Login from './Login.vue'
import Translate from './Translate.vue'
import {
  billNoOf, fileUrl, sorted, thumbUrl,
  type Invoice,
} from './types'

const authed = ref(false)
const username = ref('')
const page = ref<'invoice' | 'translate'>('invoice')
const invoices = ref<Invoice[]>([])
const drag = ref(false)
const uploading = ref(0)
const exporting = ref(false)
const preview = ref<Invoice | null>(null)
const toast = ref('')
const manualOpen = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const pwOpen = ref(false)
const pwLoading = ref(false)
const pwErr = ref('')
const pw = ref({ old: '', p1: '', p2: '' })

const manual = ref({ date: '', item: '', location: '', amount: null as number | null, note: '（工厂已付）' })
const tracker = ref<{ loaded: boolean; filename: string | null; sheets: string[] }>({
  loaded: false, filename: null, sheets: [],
})
const trackerInput = ref<HTMLInputElement | null>(null)

const showToast = (m: string) => { toast.value = m; setTimeout(() => (toast.value = ''), 2600) }

/** 与后端一致的排序 */
const ordered = computed(() => sorted(invoices.value))
const expenses = computed(() => ordered.value.filter(i => i.category === 'travel'))
const bills = computed(() => ordered.value.filter(i => i.stored_name))
const travelTotal = computed(() => {
  const amts = expenses.value.map(i => i.amount).filter((a): a is number => a !== null)
  return amts.length ? amts.reduce((s, v) => s + v, 0) : null
})

const load = () => api.list().then(r => (invoices.value = r))
const loadTracker = () => api.trackerInfo().then(r => (tracker.value = r))

function onExpired() {
  authed.value = false
  invoices.value = []
  showToast('登录已过期，请重新登录')
}

onMounted(async () => {
  window.addEventListener('auth:expired', onExpired)
  try {
    const me = await api.me()
    if (me.logged_in && me.username) {
      authed.value = true
      username.value = me.username
      load()
      loadTracker()
    }
  } catch { /* 未登录保持登录页 */ }
})
onUnmounted(() => window.removeEventListener('auth:expired', onExpired))

function onLoggedIn(u: string) {
  authed.value = true
  username.value = u
  load()
  loadTracker()
  showToast(`欢迎，${u}`)
}

async function logout() {
  await api.logout()
  authed.value = false
  invoices.value = []
}

async function submitPw() {
  pwErr.value = ''
  if (!pw.value.old) { pwErr.value = '请输入原密码'; return }
  if (pw.value.p1 !== pw.value.p2) { pwErr.value = '两次输入的新密码不一致'; return }
  if (pw.value.p1.length < 8 || !/[a-zA-Z]/.test(pw.value.p1) || !/\d/.test(pw.value.p1)) {
    pwErr.value = '新密码至少 8 位，且需同时包含字母和数字'
    return
  }
  pwLoading.value = true
  try {
    await api.changePassword(pw.value.old, pw.value.p1)
    pwOpen.value = false
    pw.value = { old: '', p1: '', p2: '' }
    showToast('密码已修改，其他设备已全部退出')
  } catch (e) {
    pwErr.value = (e as ApiError).message
  } finally {
    pwLoading.value = false
  }
}

async function onPickTracker(files: FileList | null) {
  if (!files?.length) return
  try {
    tracker.value = await api.uploadTracker(files[0])
    showToast(`Tracker 基准已加载：${tracker.value.filename}`)
  } catch (e) {
    showToast(`上传失败：${(e as Error).message}`)
  } finally {
    if (trackerInput.value) trackerInput.value.value = ''
  }
}
async function removeTracker() {
  try {
    await api.removeTracker()
    await loadTracker()
    showToast("Tracker 基准已移除")
  } catch (e) {
    showToast(`移除失败：${(e as Error).message}`)
  }
}

async function onPick(files: FileList | null) {
  if (!files?.length) return
  uploading.value = files.length
  try {
    const added = await api.upload(Array.from(files))
    await load()
    const bad = added.filter(a => !a.parse_ok || a.parse_msg)
    showToast(`已解析 ${added.length} 张${bad.length ? `，其中 ${bad.length} 张需人工核对` : ''}`)
  } catch (e) {
    showToast(`上传失败：${(e as Error).message}`)
  } finally {
    uploading.value = 0
    if (fileInput.value) fileInput.value.value = ''
  }
}
const onDrop = (e: DragEvent) => { drag.value = false; onPick(e.dataTransfer?.files ?? null) }

const val = (e: Event) => (e.target as HTMLInputElement).value
const num = (e: Event): number | null => {
  const v = (e.target as HTMLInputElement).value
  return v === '' ? null : Number(v)
}

async function upd(inv: Invoice, p: Partial<Invoice>) {
  try {
    const saved = await api.patch(inv.id, p)
    invoices.value = invoices.value.map(i => (i.id === inv.id ? saved : i))
  } catch (e) {
    showToast(`保存失败：${(e as Error).message}`)
  }
}
async function del(inv: Invoice) {
  await api.remove(inv.id)
  invoices.value = invoices.value.filter(i => i.id !== inv.id)
}
async function addManual() {
  await api.addManual({ ...manual.value, no_bill: true, category: 'travel' })
  manualOpen.value = false
  manual.value = { date: '', item: '', location: '', amount: null, note: '（工厂已付）' }
  await load()
}
async function clearAll() {
  if (!confirm('确定清空当前全部记录？（已上传的文件不会被删除）')) return
  await api.clear()
  await load()
}
async function exportXlsx() {
  exporting.value = true
  try {
    const r = await fetch('/api/export')
    if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`)
    const blob = await r.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = (r.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1]) || 'export.xlsx'
    a.click()
    URL.revokeObjectURL(a.href)
  } catch (e) {
    showToast(`导出失败：${(e as Error).message}`)
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.layout { max-width: 1200px; margin: 0 auto; padding: 18px; }
.topbar { display: flex; justify-content: space-between; align-items: center; padding: 14px 20px; }
.brand { display: flex; gap: 12px; align-items: center; }
.brand .logo { font-size: 30px; }
.brand h1 { font-size: 18px; margin: 0; }
.brand p { margin: 2px 0 0; color: var(--muted); font-size: 12px; }
.actions { display: flex; gap: 10px; align-items: center; }
.tabs { display: flex; gap: 6px; margin-left: 14px; }
.tabbtn { border: none; background: transparent; color: var(--muted); font-size: 13.5px; padding: 8px 12px; border-radius: 8px; }
.tabbtn.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
.user { font-size: 12.5px; color: var(--muted); white-space: nowrap; }

.modal-mask { position: fixed; inset: 0; background: rgba(15,23,42,.5); display: flex; align-items: center; justify-content: center; z-index: 70; }
.modal { width: 340px; padding: 22px 24px; display: flex; flex-direction: column; gap: 12px; }
.modal h3 { margin: 0; font-size: 16px; }
.modal label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); }
.modal input { border-color: var(--line); background: #fff; padding: 8px; }
.modal-err { color: var(--danger); font-size: 12.5px; }
.modal-btns { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }

.dropzone { margin: 18px 0 0; border: 2px dashed var(--line); border-radius: var(--radius); cursor: pointer; transition: all .15s; }
.dropzone.drag, .dropzone:hover { border-color: var(--accent); background: var(--accent-soft); }
.dz-inner { text-align: center; padding: 30px 16px; }
.dz-inner p { color: var(--muted); margin: 6px 0 0; font-size: 12px; }
.dz-icon { font-size: 34px; }

.tracker-bar { margin-top: 12px; padding: 10px 16px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 13px; }
.tb-label { font-weight: 600; }
.tb-name { color: var(--accent); }
.tb-hint { color: var(--muted); font-size: 12px; flex: 1; }
.tb-btn { font-size: 12px; padding: 4px 10px; }

.spinner { width: 28px; height: 28px; border: 3px solid var(--line); border-top-color: var(--accent); border-radius: 50%; margin: 0 auto 10px; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.section { margin-top: 18px; padding: 16px 20px; }
.section h2 { display: flex; gap: 8px; align-items: center; }
.section h2 .add { margin-left: auto; font-size: 12px; padding: 4px 10px; }

.manual { display: flex; flex-wrap: wrap; gap: 10px; padding: 12px; margin-bottom: 12px; background: #f9fafb; }
.manual label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.manual input { background: #fff; border-color: var(--line); }
.manual > div { display: flex; gap: 8px; align-items: flex-end; }

.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { border: 1px solid var(--line); text-align: center; padding: 4px 6px; }
th { background: #f9fafb; font-size: 13px; padding: 10px 6px; }
tbody tr:hover { background: #fafbff; }
tr.nobill { background: #fffbeb; }
td.billno { font-weight: 600; }
td input { text-align: center; }
td input[type="date"] { min-width: 108px; }
button.del { border: none; background: none; color: var(--muted); padding: 2px 6px; }
button.del:hover { color: var(--danger); }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.bill { position: relative; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.bill-no { position: absolute; top: -8px; left: -6px; background: var(--accent); color: #fff; font-weight: 700; font-size: 13px; border-radius: 8px; padding: 2px 9px; box-shadow: 0 2px 6px rgba(37,99,235,.35); }
.thumb { height: 190px; display: flex; align-items: center; justify-content: center; background: #f9fafb; border-radius: 8px; overflow: hidden; cursor: zoom-in; }
.thumb img { max-height: 100%; max-width: 100%; object-fit: contain; }
.no-thumb { color: var(--muted); text-align: center; font-size: 13px; line-height: 1.8; }
.no-thumb.big { font-size: 20px; padding: 60px; }
.meta { display: flex; flex-direction: column; gap: 6px; }
.row1 { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
.name { font-weight: 600; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.amt { color: var(--ok); font-weight: 700; white-space: nowrap; }
.row2 { display: flex; gap: 6px; }
.row2 input { background: #f9fafb; border-color: var(--line); text-align: center; }
.row3 { display: flex; gap: 6px; align-items: center; }
.row3 input { background: #f9fafb; border-color: var(--line); }
.loc { flex: 1; }
.cat { font-size: 12px; padding: 4px 8px; white-space: nowrap; }
.cat.travel { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
.warn { color: #b45309; font-size: 12px; background: #fef3c7; border-radius: 6px; padding: 4px 8px; }
.bill .del { align-self: flex-end; font-size: 12px; }

.lightbox { position: fixed; inset: 0; background: rgba(15,23,42,.72); display: flex; flex-direction: column; align-items: center; justify-content: center; z-index: 50; cursor: zoom-out; }
.lightbox img, .lightbox iframe { max-width: 92vw; max-height: 84vh; background: #fff; border-radius: 8px; border: none; }
.lightbox p { color: #e2e8f0; }

.foot { text-align: center; color: var(--muted); font-size: 12px; padding: 18px 0 6px; }
.toast { position: fixed; bottom: 26px; left: 50%; transform: translateX(-50%); background: #111827; color: #fff; padding: 10px 22px; border-radius: 999px; box-shadow: 0 8px 24px rgba(0,0,0,.25); z-index: 60; }
</style>
