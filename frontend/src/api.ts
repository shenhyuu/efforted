export type Energy = 'low' | 'mid' | 'enough'
export type DaySlot = 'morning' | 'afternoon' | 'evening' | 'night'

export interface RecordItem {
  id: number
  occurred_at: string | null
  time_scope: 'exact' | 'past'
  time_label: string | null
  day_slot: DaySlot | null
  energy: Energy | null
  content: string | null
  duration_seconds: number | null
  ash: boolean
  created_at: string
  pending?: boolean
}
export interface TimerState {
  id: number
  status: 'running' | 'paused' | 'closed'
  accumulated_seconds: number
  elapsed_seconds: number
  created_at: string
  closed_at: string | null
  break_card?: { message: string }
}
export interface Lamp {
  id: number
  message: string
  energy_at_write: Energy | null
  created_at: string
  opened_at: string | null
}
export interface Settings {
  low_energy_mode: boolean
  hide_all_numbers: boolean
  nothing_mode: boolean
  privacy_mode: boolean
}

const TOKEN_KEY = 'zhihen_token'
const QUEUE_KEY = 'zhihen_offline_checkins'
export const token = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (value: string) => localStorage.setItem(TOKEN_KEY, value),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

function errorMessage(payload: unknown) {
  if (payload && typeof payload === 'object' && 'error' in payload) {
    const error = (payload as { error?: { message?: string } }).error
    if (error?.message) return error.message
  }
  return '这里暂时没有回应，可以稍后再来。'
}

async function request<T>(path: string, options: RequestInit = {}, authenticated = true): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('Content-Type', 'application/json')
  if (authenticated && token.get()) headers.set('Authorization', `Bearer ${token.get()}`)
  const response = await fetch(`/api/v1${path}`, { ...options, headers })
  if (response.status === 401) {
    token.clear()
    window.dispatchEvent(new Event('zhihen-auth-expired'))
  }
  if (!response.ok) {
    let payload: unknown = null
    try { payload = await response.json() } catch { /* response has no JSON body */ }
    throw new Error(errorMessage(payload))
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

function queuedItems(): Array<Record<string, unknown>> {
  try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]') as Array<Record<string, unknown>> }
  catch { return [] }
}

export async function flushOfflineCheckins() {
  const items = queuedItems()
  if (!items.length || !token.get()) return 0
  await request('/checkins/batch', { method: 'POST', body: JSON.stringify({ items }) })
  localStorage.removeItem(QUEUE_KEY)
  return items.length
}

export const api = {
  authStatus: () => request<{ initialized: boolean }>('/auth/status', {}, false),
  setup: (password: string) => request<{ token: string }>('/auth/setup', { method: 'POST', body: JSON.stringify({ password }) }, false),
  login: (password: string) => request<{ token: string }>('/auth/login', { method: 'POST', body: JSON.stringify({ password }) }, false),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  getRecords: () => request<{ items: RecordItem[] }>('/records'),
  async checkin(input: { energy?: Energy; note?: string; client_uuid: string }) {
    try {
      return await request<RecordItem>('/checkins', { method: 'POST', body: JSON.stringify(input) })
    } catch (error) {
      if (navigator.onLine) throw error
      const createdAt = new Date().toISOString()
      const queue = queuedItems()
      queue.push({ ...input, client_created_at: createdAt })
      localStorage.setItem(QUEUE_KEY, JSON.stringify(queue))
      return { id: -Date.now(), occurred_at: createdAt, time_scope: 'exact', time_label: null,
        day_slot: null, energy: input.energy || null, content: input.note || null,
        duration_seconds: null, ash: false, created_at: createdAt, pending: true } as RecordItem
    }
  },
  backfill: (input: { day?: string; day_slot?: DaySlot; energy?: Energy; note?: string }) =>
    request<RecordItem>('/records/backfill', { method: 'POST', body: JSON.stringify(input) }),
  deleteRecord: (id: number) => request<void>(`/records/${id}`, { method: 'DELETE' }),
  comeback: () => request<{ is_comeback: boolean; card?: { message: string } }>('/comeback'),
  activeTimer: () => request<TimerState | null>('/timers/active'),
  startTimer: () => request<TimerState>('/timers', { method: 'POST' }),
  pauseTimer: (id: number) => request<TimerState>(`/timers/${id}/pause`, { method: 'POST' }),
  resumeTimer: (id: number) => request<TimerState>(`/timers/${id}/resume`, { method: 'POST' }),
  closeTimer: (id: number) => request<{ total_seconds: number; record_id: number }>(`/timers/${id}/close`, { method: 'POST' }),
  lamps: () => request<{ lamps: Lamp[]; context_note: string }>('/lamps'),
  createLamp: (message: string, energy_at_write?: Energy) => request<Lamp>('/lamps', { method: 'POST', body: JSON.stringify({ message, energy_at_write }) }),
  openLamp: (id: number) => request<Lamp>(`/lamps/${id}/open`, { method: 'POST' }),
  deleteLamp: (id: number) => request<void>(`/lamps/${id}`, { method: 'DELETE' }),
  settings: () => request<Settings>('/settings'),
  updateSettings: (input: Partial<Settings>) => request<Settings>('/settings', { method: 'PATCH', body: JSON.stringify(input) }),
  ash: () => request<{ result: string }>('/data/ash', { method: 'POST' }),
  purgeStatus: () => request<{ pending: boolean; grace_until: string | null }>('/data/purge'),
  requestPurge: () => request<{ grace_until: string }>('/data/purge', { method: 'POST', body: JSON.stringify({ confirm: true }) }),
  cancelPurge: () => request<void>('/data/purge/cancel', { method: 'POST' }),
  help: () => request<{ note: string; resources: Array<{ name: string; phone: string }> }>('/help/resources', {}, false),
  async exportJson() {
    const response = await fetch('/api/v1/data/export', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token.get()}` },
      body: JSON.stringify({ format: 'json' }),
    })
    if (!response.ok) throw new Error('数据暂时没有整理好。')
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url; link.download = 'zhihen-export.json'; link.click()
    URL.revokeObjectURL(url)
  },
}
