<script setup lang="ts">
import { ref } from 'vue'
import { useRecordsStore } from '@/stores/records'
import { useSettingsStore } from '@/stores/settings'

const records = useRecordsStore()
const settings = useSettingsStore()
const settled = ref(false)

async function checkin() {
  const record = await records.checkin({})
  if (!record) return
  settings.acknowledgeActivity()
  settled.value = true
  window.setTimeout(() => (settled.value = false), 2200)
}
</script>

<template>
  <div class="quiet-checkin">
    <span v-if="settled" role="status">这一刻已经收好了。</span>
    <button type="button" :disabled="records.saving" aria-label="留下一根线" @click="checkin">
      <i aria-hidden="true"></i><small>我在</small>
    </button>
  </div>
</template>
