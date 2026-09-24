<template>
  <div class="login-page">
    <div class="blob b1"></div>
    <div class="blob b2"></div>
    <div class="blob b3"></div>

    <form class="card" @submit.prevent="submit">
      <div class="logo">🧾</div>
      <h1>发票解析系统</h1>
      <p class="sub">上传发票 · 自动解析 · 一键生成 Expenses report</p>

      <label class="field">
        <span class="icon">👤</span>
        <input
          v-model="username"
          type="text"
          name="username"
          autocomplete="username"
          placeholder="用户名"
          autofocus
        />
      </label>

      <label class="field">
        <span class="icon">🔒</span>
        <input
          v-model="password"
          :type="showPw ? 'text' : 'password'"
          name="password"
          autocomplete="current-password"
          placeholder="密码"
        />
        <button type="button" class="eye" @click="showPw = !showPw" tabindex="-1">
          {{ showPw ? '🙈' : '👁️' }}
        </button>
      </label>

      <div v-if="error" class="error">{{ error }}</div>

      <button class="submit" type="submit" :disabled="loading">
        <span v-if="loading" class="spinner"></span>
        {{ loading ? '正在验证…' : '登 录' }}
      </button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { api, ApiError } from './api'

const emit = defineEmits<{ (e: 'logged-in', username: string): void }>()

const username = ref('')
const password = ref('')
const showPw = ref(false)
const loading = ref(false)
const error = ref('')

async function submit() {
  if (!username.value || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const r = await api.login(username.value.trim(), password.value)
    emit('logged-in', r.username)
  } catch (e) {
    error.value = (e as ApiError).message || '登录失败'
    password.value = ''
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 55%, #2563eb 100%);
  overflow: hidden;
  font-family: inherit;
}
.blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  opacity: .45;
  animation: float 14s ease-in-out infinite;
}
.b1 { width: 420px; height: 420px; background: #38bdf8; top: -120px; left: -100px; }
.b2 { width: 360px; height: 360px; background: #818cf8; bottom: -120px; right: -80px; animation-delay: -5s; }
.b3 { width: 260px; height: 260px; background: #22d3ee; bottom: 10%; left: 12%; animation-delay: -9s; }
@keyframes float {
  0%, 100% { transform: translateY(0) scale(1); }
  50% { transform: translateY(-26px) scale(1.06); }
}

.card {
  position: relative;
  width: 380px;
  max-width: calc(100vw - 40px);
  background: rgba(255, 255, 255, .97);
  border-radius: 18px;
  padding: 38px 36px 28px;
  box-shadow: 0 24px 70px rgba(2, 6, 23, .45);
  text-align: center;
  animation: pop .35s ease;
}
@keyframes pop {
  from { transform: translateY(14px) scale(.97); opacity: 0; }
  to { transform: none; opacity: 1; }
}
.logo { font-size: 44px; line-height: 1; }
h1 { font-size: 21px; margin: 10px 0 4px; color: #0f172a; letter-spacing: .5px; }
.sub { color: #64748b; font-size: 12.5px; margin: 0 0 24px; }

.field {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1.5px solid #e2e8f0;
  border-radius: 10px;
  padding: 0 12px;
  margin-bottom: 14px;
  background: #f8fafc;
  transition: border-color .15s, box-shadow .15s;
}
.field:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, .13);
  background: #fff;
}
.field .icon { font-size: 15px; opacity: .75; }
.field input {
  border: none;
  flex: 1;
  padding: 11px 2px;
  font-size: 14px;
  background: transparent;
}
.field input:focus { box-shadow: none; }
.eye {
  border: none;
  background: none;
  cursor: pointer;
  font-size: 15px;
  padding: 4px;
  opacity: .65;
}
.eye:hover { opacity: 1; }

.error {
  background: #fef2f2;
  color: #dc2626;
  border: 1px solid #fecaca;
  border-radius: 8px;
  font-size: 12.5px;
  padding: 8px 10px;
  margin-bottom: 12px;
  animation: shake .3s;
}
@keyframes shake {
  25% { transform: translateX(-5px); }
  75% { transform: translateX(5px); }
}

.submit {
  width: 100%;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #2563eb, #4f46e5);
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 4px;
  padding: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: filter .15s, transform .1s;
}
.submit:hover { filter: brightness(1.12); }
.submit:active { transform: scale(.985); }
.submit:disabled { opacity: .7; cursor: default; }

.spinner {
  width: 15px; height: 15px;
  border: 2px solid rgba(255,255,255,.4);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
