<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, type Energy, type RecordItem } from '@/api'
import type { WeaveData } from '@/api'
import WeaveCanvas from '@/components/WeaveCanvas.vue'
import { useRecordsStore } from '@/stores/records'
import { useSettingsStore } from '@/stores/settings'

const store = useRecordsStore()
const settings = useSettingsStore()
const energy = ref<Energy | undefined>()
const note = ref('')
const noteOpen = ref(false)
const settled = ref(false)
const comebackMessage = ref('')
const weave = ref<WeaveData | null>(null)
const weaveAnimation = ref(0)
const energyOptions: Array<{ value: Energy; label: string }> = [
  { value: 'low', label: '低' }, { value: 'mid', label: '中' }, { value: 'enough', label: '够用' },
]
const visibleRecords = computed(() => store.records.slice(0, 14))

function energyLabel(value: Energy | null) {
  return value ? energyOptions.find((item) => item.value === value)?.label : null
}

function recordDate(record: RecordItem) {
  if (settings.values.hide_all_numbers) return record.time_scope === 'past' ? '过去' : '曾经'
  if (record.time_scope === 'past' || !record.occurred_at) return '过去'
  const value = new Date(record.occurred_at)
  const today = new Date()
  if (value.toDateString() === today.toDateString()) {
    return value.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
  }
  return value.toLocaleDateString('zh-CN', { month: 'long', day: 'numeric' })
}

async function leaveTrace() {
  if (store.saving) return
  const result = await store.checkin({
    energy: energy.value, note: note.value.trim() || undefined,
  })
  if (result) {
    note.value = ''
    noteOpen.value = false
    settled.value = true
    window.setTimeout(() => (settled.value = false), 2600)
    if (!result.pending) {
      const refreshed = await api.weave().catch(() => null)
      if (refreshed) { weave.value = refreshed; weaveAnimation.value++ }
    }
  }
}

onMounted(async () => {
  await store.load()
  weave.value = await api.weave().catch(() => null)
  if (!settings.values.nothing_mode) {
    const result: { is_comeback: boolean; card?: { message: string } } = await api.comeback().catch(() => ({ is_comeback: false }))
    if (result.is_comeback) comebackMessage.value = result.card?.message || '你回来了。'
  }
})
</script>

<template>
  <main :class="['home-grid', { 'lite-home': settings.values.low_energy_mode }]">
    <section class="presence-card" aria-labelledby="presence-title">
      <div class="intro">
        <span class="eyebrow">{{ settings.values.low_energy_mode ? '现在' : '此刻' }}</span>
        <h1 id="presence-title">{{ settings.values.low_energy_mode ? '你还在。' : '你在这里。' }}</h1>
        <p v-if="!settings.values.low_energy_mode">不用解释，也不用留下些什么。点一下就够了。</p>
        <p v-if="comebackMessage" class="comeback-message">{{ comebackMessage }}</p>
      </div>
      <div v-if="!settings.values.low_energy_mode" class="energy-block">
        <p>现在的电量 <span>可以不选</span></p>
        <div class="energy-picker" role="group" aria-label="选择现在的电量">
          <button v-for="option in energyOptions" :key="option.value" type="button"
            :class="['energy-choice', `energy-${option.value}`, { selected: energy === option.value }]"
            :aria-pressed="energy === option.value"
            @click="energy = energy === option.value ? undefined : option.value">
            <span></span>{{ option.label }}
          </button>
        </div>
      </div>
      <button class="presence-button" type="button" :disabled="store.saving" @click="leaveTrace">
        <span class="button-glow" aria-hidden="true"></span>
        <strong>{{ store.saving ? '正在收好' : settings.values.low_energy_mode ? '我还在' : '我在' }}</strong>
        <small>留下一根线</small>
      </button>
      <div v-if="!settings.values.low_energy_mode" class="note-area">
        <button v-if="!noteOpen" class="quiet-action" type="button" @click="noteOpen = true">想留一句话</button>
        <div v-else class="note-editor">
          <label for="checkin-note">这一刻想记下什么 <span>可以留空</span></label>
          <textarea id="checkin-note" v-model="note" maxlength="500" rows="3"></textarea>
        </div>
      </div>
      <p v-if="settled" class="settled-message" role="status">这一刻已经收好了。</p>
      <p v-if="store.error" class="soft-error" role="status">{{ store.error }}</p>
      <p class="permission">不记录，也被允许。</p>
    </section>

    <section v-if="!settings.values.low_energy_mode" class="weave-card" aria-labelledby="weave-title">
      <div class="weave-heading">
        <div><span class="eyebrow">织痕布</span><h2 id="weave-title">走过的路</h2></div>
        <span class="weave-key">每一根线，都是一次出现</span>
      </div>
      <div v-if="store.loading" class="empty-weave">正在轻轻展开。</div>
      <div v-else-if="!store.hasRecords" class="empty-weave">
        <div class="empty-lines" aria-hidden="true"><i></i><i></i><i></i></div>
        <p>这里还很空，也很好。</p><span>留白也是生命的一部分。</span>
      </div>
      <WeaveCanvas v-if="weave" :weave="weave" :animate-key="weaveAnimation" />
      <ol v-if="store.hasRecords" class="thread-list compact-thread-list">
        <li v-for="(record, index) in visibleRecords" :key="record.id"
          :class="['thread-row', `thread-${record.energy || 'plain'}`, { fresh: store.lastAddedId === record.id }]"
          :style="{ '--thread-index': index }">
          <time>{{ recordDate(record) }}</time>
          <div class="thread" aria-hidden="true"><i></i><i></i></div>
          <span class="record-note">{{ record.content || '在这里' }}<small v-if="record.pending"> · 等待同步</small></span>
          <span v-if="energyLabel(record.energy)" class="record-energy">{{ energyLabel(record.energy) }}</span>
        </li>
      </ol>
      <footer v-if="store.hasRecords" class="weave-footer">痕迹会慢慢变多，也可以停在这里。</footer>
    </section>
  </main>
</template>
