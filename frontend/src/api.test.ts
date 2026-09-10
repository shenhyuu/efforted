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
})
