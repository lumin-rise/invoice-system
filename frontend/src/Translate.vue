<template>
  <div>
    <!-- 翻译服务设置 -->
    <section class="section card">
      <h2>翻译设置
        <span class="tag">填写任一服务商密钥后即可使用；推荐腾讯云机器翻译（每月 500 万字符免费）</span>
        <button class="testbtn" @click="testEngine" :disabled="testing">
          {{ testing ? '测试中…' : '测试连接' }}
        </button>
      </h2>
      <div class="cfg">
        <label>服务商
          <select v-model="cfg.provider">
            <option value="">（未选择）</option>
            <option v-for="(desc, key) in cfg.providers" :key="key" :value="key">{{ key }} — {{ desc }}</option>
          </select>
        </label>
        <template v-if="cfg.provider === 'tencent'">
          <label>SecretId <input v-model="keys.tencent.secret_id" placeholder="腾讯云 API 密钥 ID" /></label>
          <label>SecretKey <input v-model="keys.tencent.secret_key" type="password" placeholder="腾讯云 API 密钥 Key" /></label>
        </template>
        <template v-else-if="cfg.provider === 'baidu'">
          <label>APP ID <input v-model="keys.baidu.app_id" placeholder="百度翻译 APP ID" /></label>
          <label>APP KEY <input v-model="keys.baidu.app_key" type="password" placeholder="百度翻译密钥" /></label>
        </template>
        <template v-else-if="cfg.provider === 'deepl'">
          <label>API Key <input v-model="keys.deepl.api_key" type="password" placeholder="DeepL API Key" /></label>
        </template>
        <template v-else-if="cfg.provider === 'bing'">
          <p class="tip">Bing 免费接口无需密钥，但国内网络大多无法访问，仅作备选。</p>
        </template>
        <div>
          <button class="primary" @click="saveCfg" :disabled="saving">{{ saving ? '保存中…' : '保存设置' }}</button>
          <span v-if="testResult" :class="['result', testResult.ok ? 'ok' : 'bad']">
            {{ testResult.ok ? `✓ 连接成功，示例：${testResult.sample}` : '✗ ' + testResult.msg }}
          </span>
        </div>
      </div>
    </section>

    <!-- 上传 -->
    <div class="dropzone card" :class="{ drag }" @dragover.prevent="drag = true" @dragleave="drag = false"
         @drop.prevent="onDrop" @click="fileInput?.click()">
      <input ref="fileInput" type="file" accept=".pdf,.docx" style="display:none"
             @change="e => onPick((e.target as HTMLInputElement).files)" />
      <div v-if="!busy" class="dz-inner">
        <div class="dz-icon">🌐</div>
        <b>拖入 PDF 或 Word 文档，翻译成中文</b>
        <p>输出为 .docx（保留标题与表格结构）；旧版 .doc 请先另存为 .docx</p>
      </div>
      <div v-else class="dz-inner">
        <div class="spinner"></div>
        <b>正在翻译，请稍候…（取决于文档大小与翻译接口限频）</b>
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
            <td class="meta">{{ it.blocks }} 个段落/表格块</td>
            <td class="ops">
              <a class="btn" :href="`/api/translate/download/${it.id}`">下载中文版</a>
              <button class="danger del" @click="del(it)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { api, ApiError } from './api'

interface TxItem { id: string; name: string; created_at: number; blocks: number; download_name: string }

const cfg = reactive<any>({ provider: '', providers: {} })
const keys = reactive<any>({ tencent: {}, baidu: {}, deepl: {}, bing: {} })
const testing = ref(false), saving = ref(false), busy = ref(false), drag = ref(false)
const testResult = ref<any>(null)
const list = ref<TxItem[]>([])
const fileInput = ref<HTMLInputElement | null>(null)

const load = () => api.translateConfig().then((r: any) => {
  cfg.provider = r.provider; cfg.providers = r.providers
  for (const p of Object.keys(keys)) keys[p] = { ...(r.keys?.[p] || {}) }
})
const loadList = () => api.translateList().then(r => (list.value = r))
onMounted(() => { load(); loadList() })

async function saveCfg() {
  saving.value = true
  try {
    const r = await api.saveTranslateConfig({ provider: cfg.provider, keys })
    cfg.provider = r.provider
    testResult.value = null
    showToastSafe('设置已保存')
  } catch (e) { showToastSafe('保存失败：' + (e as ApiError).message) } finally { saving.value = false }
}
async function testEngine() {
  testing.value = true
  try { testResult.value = await api.testTranslateEngine() } catch (e) { testResult.value = { ok: false, msg: (e as ApiError).message } } finally { testing.value = false }
}

const emit = defineEmits<{ (e: 'toast', m: string): void }>()
const showToastSafe = (m: string) => emit('toast', m)

async function uploadOne(file: File) {
  busy.value = true
  try {
    const item = await api.translateUpload(file)
    await loadList()
    emit('toast', `翻译完成：${item.download_name}`)
  } catch (e) { emit('toast', '翻译失败：' + (e as ApiError).message) } finally { busy.value = false }
}
const onDrop = (e: DragEvent) => { drag.value = false; const f = e.dataTransfer?.files?.[0]; if (f) uploadOne(f) }
const onPick = (files: FileList | null) => { if (files?.length) uploadOne(files[0]) }
async function del(it: TxItem) {
  await api.translateDelete(it.id); await loadList()
}
</script>

<style scoped>
.cfg { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }
.cfg label { display: flex; flex-direction: column; gap: 5px; font-size: 12px; color: var(--muted); min-width: 200px; flex: 1; }
.cfg input, .cfg select { border-color: var(--line); background: #fff; padding: 8px; }
.tip { color: var(--muted); font-size: 12px; margin: 0; }
.testbtn { margin-left: auto; font-size: 12px; }
.result { font-size: 12.5px; align-self: center; }
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
.btn { color: var(--accent); text-decoration: none; margin-right: 10px; }
.del { font-size: 12px; }
.empty { text-align: center; color: var(--muted); padding: 26px 0; }
</style>
