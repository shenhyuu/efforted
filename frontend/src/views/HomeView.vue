<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, type ComebackData, type Energy, type RecordItem } from '@/api'
import type { WeaveData } from '@/api'
import WeaveCanvas from '@/components/WeaveCanvas.vue'
import EffortUnitPicker from '@/components/EffortUnitPicker.vue'
import ComebackCard from '@/components/ComebackCard.vue'
import { useSpeechNote } from '@/composables/useSpeechNote'
import { useRecordsStore } from '@/stores/records'
import { useSettingsStore } from '@/stores/settings'

const store = useRecordsStore()
const settings = useSettingsStore()
const router = useRouter()
const energy = ref<Energy | undefined>()
const note = ref('')
const effortUnit = ref<string | undefined>()
const noteOpen = ref(false)
const settled = ref(false)
const comeback = ref<ComebackData>({ is_comeback: false })
const echoMessage = ref('')
const speech = useSpeechNote(note)
const weave = ref<WeaveData | null>(null)
const weaveAnimation = ref(0)
const energyOptions: Array<{ value: Energy; label: string }> = [
  { value: 'low', label: '低' }, { value: 'mid', label: '中' }, { value: 'enough', label: '够用' },
]
const visibleRecords = computed(() => store.records.slice(0, 14))
const todayCount = computed(() => {
  const today = new Date().toISOString().slice(0, 10)
  const wovenToday = weave.value?.days.find((item) => item.day === today)
  if (wovenToday) return wovenToday.threads.reduce((total, thread) => total + thread.count, 0)
  return store.records.filter((record) => record.occurred_at?.slice(0, 10) === today).length
})
const energyMix = computed(() => {
  const recent = store.records.slice(0, 7).filter((record) => record.energy)
  if (!recent.length) return '还没有定义'
  const counts = recent.reduce<Record<string, number>>((all, record) => {
    if (record.energy) all[record.energy] = (all[record.energy] || 0) + 1
    return all
  }, {})
  const value = Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] as Energy | undefined
  return value ? `${energyLabel(value)}电量居多` : '还没有定义'
})

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

function recordText(record: RecordItem) {
  return [record.effort_unit, record.content].filter(Boolean).join(' · ') || '在这里'
}

function chooseComeback(choice: 'backfill' | 'fresh') {
  if (choice === 'backfill') void router.push('/backfill')
  else comeback.value = { is_comeback: false }
}

function openDay(day: string | null) {
  void router.push(day ? { path: '/timeline', query: { day } } : '/timeline')
}

async function leaveTrace() {
  if (store.saving) return
  const result = await store.checkin({
    energy: energy.value, note: note.value.trim() || undefined, effort_unit: effortUnit.value,
  })
  if (result) {
    settings.acknowledgeActivity()
    note.value = ''
    effortUnit.value = undefined
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
    comeback.value = await api.comeback().catch(() => ({ is_comeback: false }))
  }
  const delivered = await api.echo().catch(() => ({ echo: null }))
  if (delivered.echo) {
    echoMessage.value = delivered.echo.message
    if ('Notification' in window && Notification.permission === 'granted') {
      new Notification(delivered.echo.title, { body: delivered.echo.message, tag: 'zhihen-echo' })
    }
  }
})
</script>

<template>
  <main :class="['home-grid', { 'lite-home': settings.lowEnergyActive }]">
    <header v-if="!settings.lowEnergyActive" class="home-welcome">
      <div><span class="eyebrow">今日的留白</span><p>不用赶路，先确认自己在这里。</p></div>
      <div class="welcome-line" aria-hidden="true"><i></i><i></i><i></i></div>
    </header>
    <section class="presence-card" aria-labelledby="presence-title">
      <div class="intro">
        <span class="eyebrow">{{ settings.lowEnergyActive ? '现在' : '此刻' }}</span>
        <h1 id="presence-title">{{ settings.lowEnergyActive ? '你还在。' : '你在这里。' }}</h1>
        <p v-if="!settings.lowEnergyActive">不用解释，也不用留下些什么。点一下就够了。</p>
        <p v-if="echoMessage" class="comeback-message">{{ echoMessage }}</p>
      </div>
      <ComebackCard :comeback="comeback" @choose="chooseComeback" />
      <div v-if="!settings.lowEnergyActive" class="energy-block">
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
      <EffortUnitPicker v-if="!settings.lowEnergyActive" v-model="effortUnit" />
      <button class="presence-button" type="button" :disabled="store.saving" @click="leaveTrace">
        <span class="button-glow" aria-hidden="true"></span>
        <strong>{{ store.saving ? '正在收好' : settings.lowEnergyActive ? '我还在' : '我在' }}</strong>
        <small>留下一根线</small>
      </button>
      <div v-if="!settings.lowEnergyActive" class="note-area">
        <button v-if="!noteOpen" class="quiet-action" type="button" @click="noteOpen = true">想留一句话</button>
        <div v-else class="note-editor">
          <label for="checkin-note">这一刻想记下什么 <span>可以留空</span></label>
          <textarea id="checkin-note" v-model="note" maxlength="500" rows="3"></textarea>
          <button v-if="speech.supported" class="quiet-action speech-action" type="button" @click="speech.toggle">
            {{ speech.listening ? '停在这里' : '用声音记下' }}
          </button>
          <small v-if="speech.message" class="speech-message">{{ speech.message }}</small>
        </div>
      </div>
      <p v-if="settled" class="settled-message" role="status">这一刻已经收好了。</p>
      <p v-if="store.error" class="soft-error" role="status">{{ store.error }}</p>
      <p class="permission">不记录，也被允许。</p>
    </section>

    <section v-if="!settings.lowEnergyActive" class="weave-card" aria-labelledby="weave-title">
      <div class="weave-heading">
        <div><span class="eyebrow">织痕布</span><h2 id="weave-title">走过的路</h2></div>
        <span class="weave-key"><i></i>每一根线，都是一次出现</span>
      </div>
      <div v-if="store.hasRecords" class="weave-summary" aria-label="最近的织痕概览">
        <div><span>今日</span><strong>{{ settings.values.hide_all_numbers ? '有来过' : `${todayCount} 根线` }}</strong></div>
        <div><span>近七次</span><strong>{{ energyMix }}</strong></div>
        <div><span>同步</span><strong>{{ store.records.some((item) => item.pending) ? '等待联结' : '已收好' }}</strong></div>
      </div>
      <div v-if="store.loading" class="empty-weave">正在轻轻展开。</div>
      <div v-else-if="!store.hasRecords" class="empty-weave">
        <div class="empty-lines" aria-hidden="true"><i></i><i></i><i></i></div>
        <p>这里还很空，也很好。</p><span>留白也是生命的一部分。</span>
      </div>
      <WeaveCanvas v-if="weave" :weave="weave" :animate-key="weaveAnimation" @select-day="openDay" />
      <ol v-if="store.hasRecords" class="thread-list compact-thread-list">
        <li v-for="(record, index) in visibleRecords" :key="record.id"
          :class="['thread-row', `thread-${record.energy || 'plain'}`, { fresh: store.lastAddedId === record.id }]"
          :style="{ '--thread-index': index }">
          <time>{{ recordDate(record) }}</time>
          <div class="thread" aria-hidden="true"><i></i><i></i></div>
          <span class="record-note">{{ recordText(record) }}<small v-if="record.pending"> · 等待同步</small></span>
          <span v-if="energyLabel(record.energy)" class="record-energy">{{ energyLabel(record.energy) }}</span>
        </li>
      </ol>
      <RouterLink v-if="store.hasRecords" class="timeline-link" to="/timeline">展开全部痕迹</RouterLink>
      <footer v-if="store.hasRecords" class="weave-footer">痕迹会慢慢变多，也可以停在这里。</footer>
    </section>
  </main>
</template>
