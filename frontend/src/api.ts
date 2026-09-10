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
export interface WeaveThread { energy: Energy | null; count: number }
export interface WeaveData {
  days: Array<{ day: string; threads: WeaveThread[] }>
  past: { label: string; threads: WeaveThread[] }
  ember: { temperature: number }
}

const TOKEN_KEY = 'zhihen_token'
const QUEUE_DB = 'zhihen-offline'
const QUEUE_STORE = 'checkins'
interface QueuedCheckin {
  client_uuid: string
  client_created_at: string
  energy?: Energy
  note?: string
}

class ApiResponseError extends Error {}
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
    throw new ApiResponseError(errorMessage(payload))
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

function queueDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const open = indexedDB.open(QUEUE_DB, 1)
    open.onupgradeneeded = () => {
      if (!open.result.objectStoreNames.contains(QUEUE_STORE)) {
        open.result.createObjectStore(QUEUE_STORE, { keyPath: 'client_uuid' })
      }
    }
    open.onsuccess = () => resolve(open.result)
    open.onerror = () => reject(open.error)
  })
}

async function queuedItems(): Promise<QueuedCheckin[]> {
  const database = await queueDatabase()
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(QUEUE_STORE, 'readonly')
    const request = transaction.objectStore(QUEUE_STORE).getAll()
    request.onsuccess = () => resolve(request.result as QueuedCheckin[])
    request.onerror = () => reject(request.error)
    transaction.oncomplete = () => database.close()
  })
}

async function enqueue(item: QueuedCheckin): Promise<void> {
  const database = await queueDatabase()
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(QUEUE_STORE, 'readwrite')
    transaction.objectStore(QUEUE_STORE).put(item)
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(transaction.error)
  })
  database.close()
}

async function removeQueued(ids: string[]): Promise<void> {
  const database = await queueDatabase()
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(QUEUE_STORE, 'readwrite')
    const store = transaction.objectStore(QUEUE_STORE)
    ids.forEach((id) => store.delete(id))
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(transaction.error)
  })
  database.close()
}

export async function flushOfflineCheckins() {
  const items = await queuedItems()
  if (!items.length || !token.get()) return 0
  await request('/checkins/batch', { method: 'POST', body: JSON.stringify({ items }) })
  await removeQueued(items.map((item) => item.client_uuid))
  return items.length
}

export async function offlineQueuedRecords(): Promise<RecordItem[]> {
  return (await queuedItems()).map((item) => ({
    id: -Math.abs(hashId(item.client_uuid)), occurred_at: item.client_created_at,
    time_scope: 'exact', time_label: null, day_slot: null, energy: item.energy || null,
    content: item.note || null, duration_seconds: null, ash: false,
    created_at: item.client_created_at, pending: true,
  }))
}

function hashId(value: string) {
  let hash = 0
  for (let index = 0; index < value.length; index++) hash = ((hash << 5) - hash + value.charCodeAt(index)) | 0
  return hash || 1
}

export const api = {
  authStatus: () => request<{ initialized: boolean }>('/auth/status', {}, false),
  setup: (password: string) => request<{ token: string }>('/auth/setup', { method: 'POST', body: JSON.stringify({ password }) }, false),
  login: (password: string) => request<{ token: string }>('/auth/login', { method: 'POST', body: JSON.stringify({ password }) }, false),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  getRecords: (offset = 0) => request<{ items: RecordItem[]; next_cursor: number | null }>(`/records?limit=200&offset=${offset}`),
  async getAllRecords() {
    const items: RecordItem[] = []
    let offset = 0
    do {
      const page = await request<{ items: RecordItem[]; next_cursor: number | null }>(`/records?limit=200&offset=${offset}`)
      items.push(...page.items)
      if (page.next_cursor === null) break
      offset = page.next_cursor
    } while (true)
    return items
  },
  weave: () => request<WeaveData>('/weave'),
  async checkin(input: { energy?: Energy; note?: string; client_uuid: string }) {
    try {
      return await request<RecordItem>('/checkins', { method: 'POST', body: JSON.stringify(input) })
    } catch (error) {
      if (error instanceof ApiResponseError) throw error
      const createdAt = new Date().toISOString()
      await enqueue({ ...input, client_created_at: createdAt })
      return (await offlineQueuedRecords()).find((item) => item.occurred_at === createdAt) as RecordItem
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
