<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, type DaySlot, type Energy } from '@/api'

const router = useRouter()
const day = ref(''), daySlot = ref<DaySlot | undefined>(), energy = ref<Energy | undefined>(), note = ref('')
const busy = ref(false), message = ref('')
const slots: Array<{ value: DaySlot; label: string }> = [
  { value: 'morning', label: '早上' }, { value: 'afternoon', label: '下午' },
  { value: 'evening', label: '晚上' }, { value: 'night', label: '深夜' },
]
async function save() {
  busy.value = true
  try {
    await api.backfill({ day: day.value || undefined, day_slot: daySlot.value, energy: energy.value, note: note.value || undefined })
    message.value = day.value ? '那一天已经收好了。' : '这段过去已经收好了。'
    window.setTimeout(() => router.push('/'), 900)
  } catch (reason) { message.value = reason instanceof Error ? reason.message : '这段过去暂时没有被收好。' }
  finally { busy.value = false }
}
</script>

<template>
  <main class="single-page"><section class="form-card">
    <span class="eyebrow">回溯补记</span><h1>过去也可以现在记下。</h1>
    <p class="lead">日期不确定时可以留空，它只会被放在“过去”，不会被猜成某一天。</p>
    <form class="gentle-form" @submit.prevent="save">
      <label>哪一天 <small>可以留空</small><input v-model="day" type="date" :max="new Date().toISOString().slice(0, 10)"></label>
      <fieldset><legend>大概的时段 <small>可以不选</small></legend><div class="choice-row">
        <button v-for="slot in slots" :key="slot.value" type="button" :class="{ selected: daySlot === slot.value }" @click="daySlot = daySlot === slot.value ? undefined : slot.value">{{ slot.label }}</button>
      </div></fieldset>
      <fieldset><legend>那时的电量 <small>可以不选</small></legend><div class="choice-row">
        <button v-for="item in [{v:'low',l:'低'},{v:'mid',l:'中'},{v:'enough',l:'够用'}]" :key="item.v" type="button" :class="{ selected: energy === item.v }" @click="energy = energy === item.v ? undefined : item.v as Energy">{{ item.l }}</button>
      </div></fieldset>
      <label>想留的话 <small>可以留空</small><textarea v-model="note" rows="4" maxlength="500"></textarea></label>
      <button class="primary-action" type="submit" :disabled="busy">{{ busy ? '正在收好' : '把它放进织痕' }}</button>
    </form><p class="form-message" role="status">{{ message }}</p>
  </section></main>
</template>
