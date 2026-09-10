import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api, flushOfflineCheckins, offlineQueuedRecords, type Energy, type RecordItem } from '@/api'

export const useRecordsStore = defineStore('records', () => {
  const records = ref<RecordItem[]>([])
  const loading = ref(false), saving = ref(false)
  const error = ref<string | null>(null), lastAddedId = ref<number | null>(null)
  const hasRecords = computed(() => records.value.length > 0)
  async function load() {
    loading.value = true; error.value = null
    const pending = await offlineQueuedRecords().catch(() => [])
    try {
      await flushOfflineCheckins()
      records.value = await api.getAllRecords()
    } catch (reason) {
      records.value = pending
      if (!pending.length) error.value = reason instanceof Error ? reason.message : '这里暂时没有回应。'
    }
    finally { loading.value = false }
  }
  async function checkin(input: { energy?: Energy; note?: string }) {
    saving.value = true; error.value = null
    try {
      const record = await api.checkin({ ...input, client_uuid: crypto.randomUUID() })
      records.value = [record, ...records.value.filter((item) => item.id !== record.id)]
      lastAddedId.value = record.id; return record
    } catch (reason) { error.value = reason instanceof Error ? reason.message : '这一刻暂时没有被收好。'; return null }
    finally { saving.value = false }
  }
  return { records, loading, saving, error, lastAddedId, hasRecords, load, checkin }
})
