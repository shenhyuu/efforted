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
  effort_unit: string | null
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
  pending?: boolean
}
export interface Settings {
  low_energy_mode: boolean
  auto_low_energy_mode: boolean
  auto_low_energy_active: boolean
  hide_all_numbers: boolean
  nothing_mode: boolean
  notify_enabled: boolean
  weekly_report_opt_out: boolean
  privacy_mode: boolean
}
export type SettingsUpdate = Partial<Omit<Settings, 'auto_low_energy_active'>>
export interface WeaveThread { energy: Energy | null; count: number }
export interface WeaveData {
  days: Array<{ day: string; threads: WeaveThread[] }>
  past: { label: string; threads: WeaveThread[] }
  ember: { temperature: number }
  atmosphere: { low_ratio: number }
}
export interface ComebackData {
  is_comeback: boolean
  card?: {
    last_left_at: string
    last_left_hint: string
    restart_count: number
    message: string
  }
  options?: Array<{ id: 'backfill' | 'fresh'; label: string }>
}

const TOKEN_KEY = 'zhihen_token'
const QUEUE_DB = 'zhihen-offline'
const QUEUE_STORE = 'checkins'
interface QueuedAction {
  kind?: 'checkin' | 'backfill' | 'lamp'
  client_uuid: string
  client_created_at: string
  energy?: Energy
  note?: string
  effort_unit?: string
  day?: string
  day_slot?: DaySlot
  message?: string
  energy_at_write?: Energy
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

async function queuedItems(): Promise<QueuedAction[]> {
  const database = await queueDatabase()
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(QUEUE_STORE, 'readonly')
    const request = transaction.objectStore(QUEUE_STORE).getAll()
    request.onsuccess = () => resolve(request.result as QueuedAction[])
    request.onerror = () => reject(request.error)
    transaction.oncomplete = () => database.close()
  })
}

async function enqueue(item: QueuedAction): Promise<void> {
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

export async function flushOfflineActions() {
  const items = await queuedItems()
  if (!items.length || !token.get()) return 0
  let synchronized = 0
  const checkins = items.filter((item) => !item.kind || item.kind === 'checkin')
  if (checkins.length) {
    const result = await request<{ accepted: number; duplicates_ignored: number; invalid_ignored: number }>(
      '/checkins/batch', { method: 'POST', body: JSON.stringify({ items: checkins }) },
    )
    await removeQueued(checkins.map((item) => item.client_uuid))
    synchronized += result.accepted + result.duplicates_ignored
  }
  for (const item of items.filter((candidate) => candidate.kind === 'backfill' || candidate.kind === 'lamp')) {
    const path = item.kind === 'backfill' ? '/records/backfill' : '/lamps'
    const body = item.kind === 'backfill'
      ? { client_uuid: item.client_uuid, day: item.day, day_slot: item.day_slot, energy: item.energy, note: item.note, effort_unit: item.effort_unit }
      : { client_uuid: item.client_uuid, message: item.message, energy_at_write: item.energy_at_write }
    await request(path, { method: 'POST', body: JSON.stringify(body) })
    await removeQueued([item.client_uuid])
    synchronized++
  }
  return synchronized
}

export const flushOfflineCheckins = flushOfflineActions

export async function offlineQueuedRecords(): Promise<RecordItem[]> {
  return (await queuedItems()).filter((item) => item.kind !== 'lamp').map((item) => ({
    id: -Math.abs(hashId(item.client_uuid)),
    occurred_at: item.kind === 'backfill' ? (item.day ? `${item.day}T12:00:00Z` : null) : item.client_created_at,
    time_scope: item.kind === 'backfill' && !item.day ? 'past' : 'exact',
    time_label: item.kind === 'backfill' && !item.day ? '过去' : null,
    day_slot: item.day_slot || null, energy: item.energy || null,
    content: item.note || null, duration_seconds: null, ash: false,
    effort_unit: item.effort_unit || null,
    created_at: item.client_created_at, pending: true,
  }))
}

async function offlineQueuedLamps(): Promise<Lamp[]> {
  return (await queuedItems()).filter((item) => item.kind === 'lamp').map((item) => ({
    id: -Math.abs(hashId(item.client_uuid)), message: item.message || '',
    energy_at_write: item.energy_at_write || null, created_at: item.client_created_at,
    opened_at: null, pending: true,
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
  getRecords: (offset = 0, limit = 50, day?: string) => {
    const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (day) query.set('day', day)
    return request<{ items: RecordItem[]; next_cursor: number | null }>(`/records?${query}`)
  },
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
  weave: (days = 180) => request<WeaveData>(`/weave?days=${days}`),
  async checkin(input: { energy?: Energy; note?: string; effort_unit?: string; client_uuid: string }) {
    try {
      return await request<RecordItem>('/checkins', { method: 'POST', body: JSON.stringify(input) })
    } catch (error) {
      if (error instanceof ApiResponseError) throw error
      const createdAt = new Date().toISOString()
      await enqueue({ ...input, kind: 'checkin', client_created_at: createdAt })
      return (await offlineQueuedRecords()).find((item) => item.occurred_at === createdAt) as RecordItem
    }
  },
  async backfill(input: { day?: string; day_slot?: DaySlot; energy?: Energy; note?: string; effort_unit?: string }) {
    const client_uuid = crypto.randomUUID(), client_created_at = new Date().toISOString()
    try {
      return await request<RecordItem>('/records/backfill', { method: 'POST', body: JSON.stringify({ ...input, client_uuid }) })
    } catch (error) {
      if (error instanceof ApiResponseError) throw error
      await enqueue({ ...input, kind: 'backfill', client_uuid, client_created_at })
      return (await offlineQueuedRecords()).find((item) => item.id === -Math.abs(hashId(client_uuid))) as RecordItem
    }
  },
  updateRecord: (id: number, input: { day?: string | null; day_slot?: DaySlot | null; energy?: Energy | null; content?: string | null; effort_unit?: string | null }) =>
    request<RecordItem>(`/records/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),
  deleteRecord: (id: number) => request<void>(`/records/${id}`, { method: 'DELETE' }),
  comeback: () => request<ComebackData>('/comeback'),
  activeTimer: () => request<TimerState | null>('/timers/active'),
  timerSegments: (id: number) => request<{ stops: Array<{ stopped_at: string; elapsed_seconds: number }> }>(`/timers/${id}/segments`),
  startTimer: () => request<TimerState>('/timers', { method: 'POST' }),
  pauseTimer: (id: number) => request<TimerState>(`/timers/${id}/pause`, { method: 'POST' }),
  resumeTimer: (id: number) => request<TimerState>(`/timers/${id}/resume`, { method: 'POST' }),
  closeTimer: (id: number) => request<{ total_seconds: number; record_id: number }>(`/timers/${id}/close`, { method: 'POST' }),
  async lamps() {
    const pending = await offlineQueuedLamps().catch(() => [])
    try {
      await flushOfflineActions()
      return await request<{ lamps: Lamp[]; context_note: string }>('/lamps')
    } catch (error) {
      if (pending.length) return { lamps: pending, context_note: '等待联结后，这些灯会留在这里。' }
      throw error
    }
  },
  async createLamp(message: string, energy_at_write?: Energy) {
    const client_uuid = crypto.randomUUID(), client_created_at = new Date().toISOString()
    try {
      return await request<Lamp>('/lamps', { method: 'POST', body: JSON.stringify({ message, energy_at_write, client_uuid }) })
    } catch (error) {
      if (error instanceof ApiResponseError) throw error
      await enqueue({ kind: 'lamp', client_uuid, client_created_at, message, energy_at_write })
      return (await offlineQueuedLamps()).find((item) => item.id === -Math.abs(hashId(client_uuid))) as Lamp
    }
  },
  effortUnits: () => request<{ items: string[] }>('/effort-units'),
  openLamp: (id: number) => request<Lamp>(`/lamps/${id}/open`, { method: 'POST' }),
  deleteLamp: (id: number) => request<void>(`/lamps/${id}`, { method: 'DELETE' }),
  settings: () => request<Settings>('/settings'),
  updateSettings: (input: SettingsUpdate) => request<Settings>('/settings', { method: 'PATCH', body: JSON.stringify(input) }),
  weeklyReflection: () => request<{ period: string; lines: string[] }>('/reflections/weekly', { method: 'POST' }),
  echo: () => request<{ echo: { title: string; message: string } | null }>('/echo', { method: 'POST' }),
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
