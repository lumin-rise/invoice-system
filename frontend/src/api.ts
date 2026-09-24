import type { Invoice } from './types'

export class ApiError extends Error {
  status: number
  constructor(status: number, msg: string) {
    super(msg)
    this.status = status
  }
}

async function j<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let msg = `HTTP ${r.status}`
    try { msg = (await r.json()).detail || msg } catch { /* ignore */ }
    if (r.status === 401) window.dispatchEvent(new CustomEvent('auth:expired'))
    throw new ApiError(r.status, msg)
  }
  return r.json() as Promise<T>
}

export interface MeInfo { logged_in: boolean; username: string | null }

export const api = {
  me: (): Promise<MeInfo> => fetch('/api/me').then(r => j(r)),

  login: (username: string, password: string): Promise<{ ok: boolean; username: string }> =>
    fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    }).then(r => j(r)),

  logout: (): Promise<{ ok: boolean }> =>
    fetch('/api/logout', { method: 'POST' }).then(r => j(r)),

  changePassword: (old_password: string, new_password: string): Promise<{ ok: boolean }> =>
    fetch('/api/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ old_password, new_password }),
    }).then(r => j(r)),
  list: (): Promise<Invoice[]> => fetch('/api/invoices').then(r => j(r)),

  upload: (files: File[]): Promise<Invoice[]> => {
    const fd = new FormData()
    files.forEach(f => fd.append('files', f))
    return fetch('/api/upload', { method: 'POST', body: fd }).then(r => j(r))
  },

  patch: (id: string, p: Partial<Invoice>): Promise<Invoice> =>
    fetch(`/api/invoices/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(p),
    }).then(r => j(r)),

  remove: (id: string): Promise<{ ok: boolean }> =>
    fetch(`/api/invoices/${id}`, { method: 'DELETE' }).then(r => j(r)),

  addManual: (b: Partial<Invoice>): Promise<Invoice> =>
    fetch('/api/invoices/manual', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(b),
    }).then(r => j(r)),

  clear: (): Promise<{ ok: boolean }> =>
    fetch('/api/session/clear', { method: 'POST' }).then(r => j(r)),

  trackerInfo: (): Promise<{ loaded: boolean; filename: string | null; sheets: string[] }> =>
    fetch('/api/tracker').then(r => j(r)),

  uploadTracker: (file: File): Promise<{ loaded: boolean; filename: string; sheets: string[] }> => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch('/api/tracker', { method: 'POST', body: fd }).then(r => j(r))
  },

  removeTracker: (): Promise<{ ok: boolean }> =>
    fetch('/api/tracker', { method: 'DELETE' }).then(r => j(r)),

  // ---- 文档翻译 ----
  translateConfig: (): Promise<any> => fetch('/api/translate/config').then(r => j(r)),
  saveTranslateConfig: (b: any): Promise<any> =>
    fetch('/api/translate/config', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b),
    }).then(r => j(r)),
  testTranslateEngine: (): Promise<{ ok: boolean; msg?: string; sample?: string }> =>
    fetch('/api/translate/test', { method: 'POST' }).then(r => j(r)),
  translateUpload: (file: File): Promise<any> => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch('/api/translate/upload', { method: 'POST', body: fd }).then(r => j(r))
  },
  translateList: (): Promise<any[]> => fetch('/api/translate/list').then(r => j(r)),
  translateDelete: (id: string): Promise<{ ok: boolean }> =>
    fetch(`/api/translate/${id}`, { method: 'DELETE' }).then(r => j(r)),
}
