<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, type DaySlot, type Energy, type RecordItem } from '@/api'
import EffortUnitPicker from '@/components/EffortUnitPicker.vue'

const route = useRoute()
const records = ref<RecordItem[]>([])
const loading = ref(true)
const loadingMore = ref(false)
const nextCursor = ref<number | null>(0)
const message = ref('')
const editing = ref<RecordItem | null>(null)
const editDay = ref('')
const editSlot = ref<DaySlot | undefined>()
const editEnergy = ref<Energy | undefined>()
const editContent = ref('')
const editUnit = ref<string | undefined>()
const selectedDay = computed(() => typeof route.query.day === 'string' ? route.query.day : '')
const shownRecords = computed(() => selectedDay.value
  ? records.value.filter((record) => record.occurred_at?.slice(0, 10) === selectedDay.value)
  : records.value)
const energyOptions: Array<{ value: Energy; label: string }> = [
  { value: 'low', label: '低' }, { value: 'mid', label: '中' }, { value: 'enough', label: '够用' },
]
const slotOptions: Array<{ value: DaySlot; label: string }> = [
  { value: 'morning', label: '早上' }, { value: 'afternoon', label: '下午' },
  { value: 'evening', label: '晚上' }, { value: 'night', label: '深夜' },
]

function label(record: RecordItem) {
  if (!record.occurred_at) return '过去'
  return new Date(record.occurred_at).toLocaleString('zh-CN', { month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })
}
function openEditor(record: RecordItem) {
  if (record.pending) return
  editing.value = record
  editDay.value = record.occurred_at?.slice(0, 10) || ''
  editSlot.value = record.day_slot || undefined
  editEnergy.value = record.energy || undefined
  editContent.value = record.content || ''
  editUnit.value = record.effort_unit || undefined
}
async function save() {
  if (!editing.value) return
  try {
    const updated = await api.updateRecord(editing.value.id, {
      day: editDay.value || null, day_slot: editSlot.value || null,
      energy: editEnergy.value || null, content: editContent.value.trim() || null,
      effort_unit: editUnit.value || null,
    })
    records.value = records.value.map((record) => record.id === updated.id ? updated : record)
    editing.value = null
    message.value = '这段痕迹已经收好了。'
  } catch (reason) { message.value = reason instanceof Error ? reason.message : '这段痕迹暂时没有回应。' }
}
async function remove(record: RecordItem) {
  if (!window.confirm('这段痕迹会被立即物理删除。确认继续吗？')) return
  try {
    await api.deleteRecord(record.id)
    records.value = records.value.filter((item) => item.id !== record.id)
    if (nextCursor.value !== null) nextCursor.value = Math.max(0, nextCursor.value - 1)
    if (editing.value?.id === record.id) editing.value = null
    message.value = '这段痕迹已经移走。'
  } catch (reason) { message.value = reason instanceof Error ? reason.message : '这段痕迹暂时没有回应。' }
}
async function load(reset = false) {
  if (reset) {
    records.value = []
    nextCursor.value = 0
    loading.value = true
  } else {
    if (nextCursor.value === null || loadingMore.value) return
    loadingMore.value = true
  }
  try {
    const page = await api.getRecords(nextCursor.value || 0, 50, selectedDay.value || undefined)
    records.value.push(...page.items)
    nextCursor.value = page.next_cursor
  }
  catch (reason) { message.value = reason instanceof Error ? reason.message : '痕迹流暂时没有展开。' }
  finally { loading.value = false; loadingMore.value = false }
}
onMounted(() => load(true))
watch(selectedDay, () => load(true))
</script>

<template>
  <main class="single-page"><section class="form-card wide-card timeline-card">
    <div class="page-heading"><div><span class="eyebrow">全部痕迹</span><h1>{{ selectedDay ? '这一天留下的线。' : '走过的都在这里。' }}</h1>
      <p class="lead">每一段都可以重新整理，也可以由你移走。</p></div><span class="page-number" aria-hidden="true">∞</span></div>
    <p v-if="loading" class="quiet-panel">正在轻轻展开。</p>
    <p v-else-if="!shownRecords.length" class="quiet-panel">这里还留着一段空白。</p>
    <ol v-else class="timeline-list">
      <li v-for="record in shownRecords" :key="record.id" :class="`thread-${record.energy || 'plain'}`">
        <div class="timeline-mark" aria-hidden="true"><i></i></div>
        <div><time>{{ label(record) }}</time><p>{{ [record.effort_unit, record.content].filter(Boolean).join(' · ') || '在这里' }}</p></div>
        <button type="button" :disabled="record.pending" @click="openEditor(record)">{{ record.pending ? '等待同步' : '整理' }}</button>
      </li>
    </ol>
    <button v-if="nextCursor !== null" class="quiet-action timeline-more" type="button" :disabled="loadingMore" @click="load()">
      {{ loadingMore ? '正在继续展开' : '再展开一些' }}
    </button>
    <form v-if="editing" class="gentle-form record-editor" @submit.prevent="save">
      <div class="editor-heading"><h2>整理这段痕迹</h2><button class="text-button" type="button" @click="editing = null">合上</button></div>
      <label>哪一天 <small>留空时归入过去</small><input v-model="editDay" type="date" :max="new Date().toISOString().slice(0, 10)"></label>
      <fieldset><legend>大概的时段 <small>可以不选</small></legend><div class="choice-row">
        <button v-for="slot in slotOptions" :key="slot.value" type="button" :class="{ selected: editSlot === slot.value }" @click="editSlot = editSlot === slot.value ? undefined : slot.value">{{ slot.label }}</button>
      </div></fieldset>
      <fieldset><legend>那时的电量 <small>可以不选</small></legend><div class="choice-row">
        <button v-for="item in energyOptions" :key="item.value" type="button" :class="{ selected: editEnergy === item.value }" @click="editEnergy = editEnergy === item.value ? undefined : item.value">{{ item.label }}</button>
      </div></fieldset>
      <EffortUnitPicker v-model="editUnit" />
      <label>留下的话 <small>可以留空</small><textarea v-model="editContent" rows="3" maxlength="500"></textarea></label>
      <div class="editor-actions"><button class="primary-action" type="submit">收好改动</button><button class="delete-action" type="button" @click="remove(editing)">移走这段痕迹</button></div>
    </form>
    <p class="form-message" role="status">{{ message }}</p>
  </section></main>
</template>
