<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api, type TimerState } from '@/api'

const timer = ref<TimerState | null>(null), localSeconds = ref(0), message = ref(''), busy = ref(false)
let ticker: number | undefined
const timeText = computed(() => {
  const minutes = Math.floor(localSeconds.value / 60), seconds = localSeconds.value % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
})
function syncTicker() {
  if (ticker) window.clearInterval(ticker)
  if (timer.value?.status === 'running') ticker = window.setInterval(() => localSeconds.value++, 1000)
}
async function load() { timer.value = await api.activeTimer(); localSeconds.value = timer.value?.elapsed_seconds || 0; syncTicker() }
async function start() { busy.value = true; timer.value = await api.startTimer(); localSeconds.value = timer.value.elapsed_seconds; syncTicker(); busy.value = false }
async function pause() { if (!timer.value) return; timer.value = await api.pauseTimer(timer.value.id); localSeconds.value = timer.value.elapsed_seconds; message.value = timer.value.break_card?.message || ''; syncTicker() }
async function resume() { if (!timer.value) return; timer.value = await api.resumeTimer(timer.value.id); message.value = '你回来了。'; syncTicker() }
async function close() { if (!timer.value) return; const result = await api.closeTimer(timer.value.id); localSeconds.value = result.total_seconds; timer.value = null; message.value = '今天就到这里。'; syncTicker() }
onMounted(load); onBeforeUnmount(() => { if (ticker) window.clearInterval(ticker) })
</script>

<template><main class="single-page"><section class="timer-card">
  <span class="eyebrow">弹性计时</span><h1>如果你想计个时。</h1><p class="lead">没有期限。歇一会儿之后，走过的时间仍然在。</p>
  <div :class="['breathing-orb', { active: timer?.status === 'running' }]">
    <span>{{ timer ? (timer.status === 'running' ? '此刻在走' : '先歇一会儿') : '随时可以开始' }}</span>
    <time v-if="timer">{{ timeText }}</time>
  </div>
  <div class="timer-actions">
    <button v-if="!timer" class="primary-action" type="button" :disabled="busy" @click="start">从这里开始</button>
    <template v-else><button v-if="timer.status === 'running'" class="primary-action" type="button" @click="pause">我先歇一会儿</button>
    <button v-else class="primary-action" type="button" @click="resume">我回来了</button>
    <button class="secondary-action" type="button" @click="close">今天就到这里</button></template>
  </div><p class="form-message">{{ message }}</p>
</section></main></template>
