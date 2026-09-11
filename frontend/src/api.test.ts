import 'fake-indexeddb/auto'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api, flushOfflineCheckins, offlineQueuedRecords, token } from './api'

async function clearQueue() {
  await new Promise<void>((resolve) => {
    const request = indexedDB.deleteDatabase('zhihen-offline')
    request.onsuccess = () => resolve()
    request.onerror = () => resolve()
    request.onblocked = () => resolve()
  })
}

describe('offline check-in queue', () => {
  beforeEach(async () => {
    await clearQueue()
    localStorage.clear()
    token.set('test-token')
  })

  it('keeps a network failure in IndexedDB and returns an optimistic record', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    const record = await api.checkin({ client_uuid: 'offline-1', energy: 'low' })
    expect(record.pending).toBe(true)
    expect((await offlineQueuedRecords())).toHaveLength(1)
  })

  it('removes only a successfully synchronized batch', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    await api.checkin({ client_uuid: 'offline-2' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ accepted: 1, duplicates_ignored: 0 }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    })))
    expect(await flushOfflineCheckins()).toBe(1)
    expect(await offlineQueuedRecords()).toHaveLength(0)
  })

  it('clears a mixed batch after the server isolates an invalid timestamp', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    await api.checkin({ client_uuid: 'offline-3' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      accepted: 0, duplicates_ignored: 0, invalid_ignored: 1,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
    expect(await flushOfflineCheckins()).toBe(0)
    expect(await offlineQueuedRecords()).toHaveLength(0)
  })

  it('keeps a backfill during a network failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    const record = await api.backfill({ note: '那段过去' })
    expect(record.pending).toBe(true)
    expect(record.time_scope).toBe('past')
    expect((await offlineQueuedRecords())[0]?.content).toBe('那段过去')
  })

  it('keeps a lamp during a network failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    const lamp = await api.createLamp('留给以后', 'low')
    expect(lamp.pending).toBe(true)
    const shelf = await api.lamps()
    expect(shelf.lamps[0]?.message).toBe('留给以后')
  })
})
