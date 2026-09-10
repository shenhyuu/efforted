<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api, type TimerState } from '@/api'
import { useSettingsStore } from '@/stores/settings'

const timer = ref<TimerState | null>(null), localSeconds = ref(0), message = ref(''), busy = ref(false)
const settings = useSettingsStore()
const numbersVisible = ref(false)
const snapshotKey = 'zhihen_timer_snapshot'
let ticker: number | undefined
const timeText = computed(() => {
  const minutes = Math.floor(localSeconds.value / 60), seconds = localSeconds.value % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
})
function syncTicker() {
  if (ticker) window.clearInterval(ticker)
  if (timer.value?.status === 'running') ticker = window.setInterval(() => localSeconds.value++, 1000)
}
function persistSnapshot() {
  if (!timer.value) return localStorage.removeItem(snapshotKey)
  localStorage.setItem(snapshotKey, JSON.stringify({
    timer: { ...timer.value, elapsed_seconds: localSeconds.value }, savedAt: Date.now(),
  }))
}
function restoreSnapshot() {
  try {
    const snapshot = JSON.parse(localStorage.getItem(snapshotKey) || '') as { timer: TimerState; savedAt: number }
    timer.value = snapshot.timer
    localSeconds.value = snapshot.timer.elapsed_seconds
      + (snapshot.timer.status === 'running' ? Math.max(0, Math.floor((Date.now() - snapshot.savedAt) / 1000)) : 0)
    syncTicker()
  } catch { localStorage.removeItem(snapshotKey) }
}
async function perform(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; message.value = ''
  try { await action() }
  catch (reason) { message.value = reason instanceof Error ? reason.message : '这段计时暂时没有回应。' }
  finally { busy.value = false }
}
async function load() { restoreSnapshot(); await perform(async () => { timer.value = await api.activeTimer(); localSeconds.value = timer.value?.elapsed_seconds || 0; persistSnapshot(); syncTicker() }) }
async function start() { await perform(async () => { timer.value = await api.startTimer(); localSeconds.value = timer.value.elapsed_seconds; persistSnapshot(); syncTicker() }) }
async function pause() { if (!timer.value) return; await perform(async () => { timer.value = await api.pauseTimer(timer.value!.id); localSeconds.value = timer.value.elapsed_seconds; message.value = timer.value.break_card?.message || ''; persistSnapshot(); syncTicker() }) }
async function resume() { if (!timer.value) return; await perform(async () => { timer.value = await api.resumeTimer(timer.value!.id); message.value = '你回来了。'; persistSnapshot(); syncTicker() }) }
async function close() { if (!timer.value) return; await perform(async () => { const result = await api.closeTimer(timer.value!.id); localSeconds.value = result.total_seconds; timer.value = null; persistSnapshot(); message.value = '今天就到这里。'; syncTicker() }) }
onMounted(load); onBeforeUnmount(() => { persistSnapshot(); if (ticker) window.clearInterval(ticker) })
</script>

<template><main class="single-page"><section class="timer-card">
  <div class="page-heading"><div><span class="eyebrow">弹性计时</span><h1>如果你想计个时。</h1><p class="lead">没有期限。歇一会儿之后，走过的时间仍然在。</p></div><span class="page-number" aria-hidden="true">02</span></div>
  <div :class="['breathing-orb', { active: timer?.status === 'running' }]">
    <i class="orb-ring ring-one" aria-hidden="true"></i><i class="orb-ring ring-two" aria-hidden="true"></i>
    <span>{{ timer ? (timer.status === 'running' ? '此刻在走' : '先歇一会儿') : '随时可以开始' }}</span>
    <time v-if="timer && numbersVisible && !settings.values.hide_all_numbers">{{ timeText }}</time>
  </div>
  <button v-if="timer && !settings.values.hide_all_numbers" class="text-button timer-number-toggle" type="button" @click="numbersVisible = !numbersVisible">
    {{ numbersVisible ? '收起走过的时间' : '看看走了多久' }}
  </button>
  <div class="timer-actions">
    <button v-if="!timer" class="primary-action" type="button" :disabled="busy" @click="start">从这里开始</button>
    <template v-else><button v-if="timer.status === 'running'" class="primary-action" type="button" :disabled="busy" @click="pause">我先歇一会儿</button>
    <button v-else class="primary-action" type="button" :disabled="busy" @click="resume">我回来了</button>
    <button class="secondary-action" type="button" :disabled="busy" @click="close">今天就到这里</button></template>
  </div><p class="form-message">{{ message }}</p>
  <div class="timer-principles" aria-label="计时说明"><span>可以暂停</span><i></i><span>不设目标</span><i></i><span>走过的都算数</span></div>
</section></main></template>
