<template>
  <div>
    <!-- 引擎设置（免费，无需密钥） -->
    <section class="section card">
      <h2>翻译引擎
        <span class="tag">MyMemory 免费接口，无需任何密钥；填邮箱可将每日额度从 5 千提升到 5 万字符</span>
        <button class="testbtn" @click="testEngine" :disabled="testing">
          {{ testing ? '测试中…' : '测试连接' }}
        </button>
      </h2>
      <div class="cfg">
        <label>通知邮箱（选填）
          <input v-model="email" placeholder="your@email.com" />
        </label>
        <button class="primary" @click="saveCfg" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
        <span v-if="testResult" :class="['result', testResult.ok ? 'ok' : 'bad']">
          {{ testResult.ok ? `✓ 引擎正常，示例：${testResult.sample}` : '✗ ' + testResult.msg }}
        </span>
      </div>
    </section>

    <!-- 上传 -->
    <div class="dropzone card" :class="{ drag }" @dragover.prevent="drag = true" @dragleave="drag = false"
         @drop.prevent="onDrop" @click="fileInput?.click()">
      <input ref="fileInput" type="file" accept=".pdf,.docx" style="display:none"
             @change="e => onPick((e.target as HTMLInputElement).files)" />
      <div v-if="!busy" class="dz-inner">
        <div class="dz-icon">🌐</div>
        <b>拖入 PDF 或 Word 文档，翻译成中文（原文+译文对照）</b>
        <p>可在线浏览，也可下载双语 Word；旧版 .doc 请先另存为 .docx</p>
      </div>
      <div v-else class="dz-inner">
        <div class="spinner"></div>
        <b>正在翻译（{{ progress }}），完成后自动出现在下方列表…</b>
      </div>
    </div>

    <!-- 历史记录 -->
    <section class="section card">
      <h2>翻译记录 <span class="badge">{{ list.length }} 份</span></h2>
      <div v-if="!list.length" class="empty">还没有翻译记录</div>
      <table v-else>
        <tbody>
          <tr v-for="it in list" :key="it.id">
            <td class="name">{{ it.name }}</td>
            <td class="date">{{ new Date(it.created_at * 1000).toLocaleString() }}</td>
            <td class="meta">{{ it.blocks }} 块</td>
            <td class="ops">
              <button class="btn" @click="read(it)">在线浏览</button>
              <a class="btn" :href="`/api/translate/download/${it.id}`">下载双语 Word</a>
              <button class="danger del" @click="del(it)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 在线阅读器 -->
    <teleport to="body">
      <div v-if="reader" class="reader-mask" @click.self="reader = null">
        <div class="reader">
          <div class="rd-head">
            <b>{{ reader.name }}</b>
            <div class="rd-tools">
              <button :class="{ on: !onlyCn }" @click="onlyCn = false">双语</button>
              <button :class="{ on: onlyCn }" @click="onlyCn = true">仅中文</button>
              <a class="btn" :href="`/api/translate/download/${reader.id}`">下载 Word</a>
              <button @click="reader = null">✕</button>
            </div>
          </div>
          <div class="rd-body">
            <template v-for="(b, i) in reader.content" :key="i">
              <h3 v-if="b.type === 'heading'" :class="'lv' + b.level">
                {{ b.dst }}<span v-if="!onlyCn && b.src" class="src"> {{ b.src }}</span>
              </h3>
              <div v-else-if="b.type === 'para'" class="para">
                <p class="dst">{{ b.dst }}</p>
                <p v-if="!onlyCn && b.src" class="src">{{ b.src }}</p>
              </div>
              <table v-else class="tbl">
                <tr v-for="(row, ri) in b.cells" :key="ri">
                  <td v-for="(c, ci) in row" :key="ci">
                    <div class="dst">{{ c.dst }}</div>
                    <div v-if="!onlyCn && c.src && c.src !== c.dst" class="src">{{ c.src }}</div>
                  </td>
                </tr>
              </table>
            </template>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, ApiError } from './api'

interface TxItem { id: string; name: string; created_at: number; blocks: number; download_name: string }

const email = ref('')
const testing = ref(false), saving = ref(false), busy = ref(false), drag = ref(false)
const testResult = ref<any>(null)
const list = ref<TxItem[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const reader = ref<any>(null)
const onlyCn = ref(false)
const progress = ref('')
const emit = defineEmits<{ (e: 'toast', m: string): void }>()

const load = () => api.translateConfig().then((r: any) => (email.value = r.email || ''))
const loadList = () => api.translateList().then(r => (list.value = r))
onMounted(() => { load(); loadList() })

async function saveCfg() {
  saving.value = true
  try { await api.saveTranslateConfig({ email: email.value }); emit('toast', '已保存') }
  catch (e) { emit('toast', '保存失败：' + (e as ApiError).message) } finally { saving.value = false }
}
async function testEngine() {
  testing.value = true
  try { testResult.value = await api.testTranslateEngine() }
  catch (e) { testResult.value = { ok: false, msg: (e as ApiError).message } }
  finally { testing.value = false }
}

async function uploadOne(file: File) {
  busy.value = true
  progress.value = '提取文本并调用翻译接口'
  const timer = setInterval(() => { progress.value += '…' }, 3000)
  try {
    const item = await api.translateUpload(file)
    await loadList()
    emit('toast', `翻译完成：${item.download_name}`)
    const fresh = list.value.find(x => x.id === item.id)
    if (fresh) read(fresh)          // 完成后直接打开在线浏览
  } catch (e) {
    emit('toast', '翻译失败：' + (e as ApiError).message)
  } finally { clearInterval(timer); busy.value = false }
}
const onDrop = (e: DragEvent) => { drag.value = false; const f = e.dataTransfer?.files?.[0]; if (f) uploadOne(f) }
const onPick = (files: FileList | null) => { if (files?.length) uploadOne(files[0]) }

async function read(it: TxItem) {
  try {
    const data = await api.translateContent(it.id)
    reader.value = { id: it.id, name: data.name, content: data.content }
  } catch (e) { emit('toast', (e as ApiError).message) }
}
async function del(it: TxItem) {
  await api.translateDelete(it.id); await loadList()
}
</script>

<style scoped>
.cfg { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
.cfg label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); min-width: 260px; }
.cfg input { border-color: var(--line); background: #fff; padding: 8px; }
.testbtn { margin-left: auto; font-size: 12px; }
.result { font-size: 12.5px; }
.result.ok { color: var(--ok); }
.result.bad { color: var(--danger); }
.dropzone { margin: 18px 0 0; border: 2px dashed var(--line); border-radius: var(--radius); cursor: pointer; transition: all .15s; }
.dropzone.drag, .dropzone:hover { border-color: var(--accent); background: var(--accent-soft); }
.dz-inner { text-align: center; padding: 26px 16px; }
.dz-inner p { color: var(--muted); margin: 6px 0 0; font-size: 12px; }
.dz-icon { font-size: 32px; }
.spinner { width: 24px; height: 24px; border: 3px solid var(--line); border-top-color: var(--accent); border-radius: 50%; margin: 0 auto 8px; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
table { width: 100%; border-collapse: collapse; }
td { border-bottom: 1px solid var(--line); padding: 9px 8px; font-size: 13px; }
.name { font-weight: 600; }
.date, .meta { color: var(--muted); font-size: 12px; white-space: nowrap; }
.ops { text-align: right; white-space: nowrap; }
.btn { color: var(--accent); text-decoration: none; background: none; border: none; cursor: pointer; margin-right: 10px; font-size: 12.5px; }
.btn:hover { text-decoration: underline; }
.del { font-size: 12px; }
.empty { text-align: center; color: var(--muted); padding: 26px 0; }

.reader-mask { position: fixed; inset: 0; background: rgba(15,23,42,.6); z-index: 70; display: flex; align-items: center; justify-content: center; }
.reader { background: #fff; width: min(920px, 94vw); height: min(86vh, 1000px); border-radius: 12px; display: flex; flex-direction: column; overflow: hidden; }
.rd-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 12px 18px; border-bottom: 1px solid var(--line); }
.rd-tools { display: flex; gap: 8px; align-items: center; }
.rd-tools .on { background: var(--accent-soft); color: var(--accent); border-color: var(--accent); }
.rd-tools button, .rd-tools a { font-size: 12.5px; padding: 5px 10px; }
.rd-body { overflow-y: auto; padding: 22px 30px; }
.rd-body h3 { margin: 20px 0 8px; color: var(--ink); }
.rd-body h3.lv1 { font-size: 19px; }
.rd-body h3.lv2 { font-size: 16px; }
.para { margin: 10px 0; }
.dst { font-size: 14px; line-height: 1.7; }
.src { color: #9ca3af; font-size: 11.5px; line-height: 1.5; }
.tbl { width: 100%; border-collapse: collapse; margin: 12px 0; }
.tbl td { border: 1px solid var(--line); padding: 7px 9px; vertical-align: top; font-size: 12.5px; line-height: 1.55; }
</style>
