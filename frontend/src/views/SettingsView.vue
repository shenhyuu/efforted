<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, type RecordItem, type SettingsUpdate } from '@/api'
import { useSettingsStore } from '@/stores/settings'

const settings = useSettingsStore(), router = useRouter()
const purge = ref<{ pending: boolean; grace_until: string | null }>({ pending: false, grace_until: null })
const help = ref<{ note: string; resources: Array<{ name: string; phone: string }> } | null>(null)
const note = ref('')
const busy = ref(false)
async function perform(action: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; note.value = ''
  try { await action() }
  catch (reason) { note.value = reason instanceof Error ? reason.message : '这里暂时没有回应。' }
  finally { busy.value = false }
}
onMounted(async () => { await settings.load(); await perform(async () => { purge.value = await api.purgeStatus(); help.value = await api.help() }) })
async function toggle(key: keyof SettingsUpdate) {
  const updated = await settings.update({ [key]: !settings.values[key] })
  if (updated && key === 'low_energy_mode' && settings.values.low_energy_mode) await router.push('/')
}
async function toggleEcho() {
  if (settings.values.notify_enabled) {
    await settings.update({ notify_enabled: false })
    return
  }
  if (!('Notification' in window)) {
    note.value = '这个浏览器暂时不提供系统通知。'
    return
  }
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') {
    note.value = '系统通知没有开启，回声会继续保持安静。'
    return
  }
  await settings.update({ notify_enabled: true })
}
async function makeAsh() {
  if (!window.confirm('文字与灯会被立即物理删除，织痕图案仍会留下。确认继续吗？')) return
  await perform(async () => { note.value = (await api.ash()).result })
}
async function requestPurge() {
  if (!window.confirm('全部记录将在 48 小时后被物理删除。宽限期内可以撤销。确认继续吗？')) return
  await perform(async () => { const result = await api.requestPurge(); purge.value = { pending: true, grace_until: result.grace_until } })
}
async function cancelPurge() { await perform(async () => { await api.cancelPurge(); purge.value = { pending: false, grace_until: null }; note.value = '清空请求已经撤销。' }) }
async function exportPng() {
  const records = await api.getAllRecords()
  const canvas = document.createElement('canvas'), width = 1200, row = 18
  canvas.width = width; canvas.height = Math.max(720, records.length * row + 260)
  const context = canvas.getContext('2d'); if (!context) return
  context.fillStyle = '#f4efe6'; context.fillRect(0, 0, canvas.width, canvas.height)
  context.fillStyle = '#3f3a34'; context.font = '36px serif'; context.fillText('织痕', 80, 90)
  context.fillStyle = '#81776b'; context.font = '16px sans-serif'; context.fillText('那些来过的时刻，都留在这里。', 80, 130)
  const colors: Record<string, string> = { low: '#8e9aa1', mid: '#aa8a70', enough: '#8d9477', plain: '#998f83' }
  records.slice().reverse().forEach((record: RecordItem, index: number) => {
    const y = 210 + index * row; context.strokeStyle = colors[record.energy || 'plain'] ?? '#998f83'
    context.globalAlpha = 0.32 + (index / Math.max(records.length, 1)) * 0.55; context.lineWidth = 2
    context.beginPath(); context.moveTo(80, y); context.bezierCurveTo(330, y - 8, 820, y + 8, 1120, y); context.stroke()
  })
  context.globalAlpha = 1
  const link = document.createElement('a'); link.download = 'zhihen-scroll.png'; link.href = canvas.toDataURL('image/png'); link.click()
}
</script>

<template><main class="single-page settings-page"><section class="form-card wide-card">
  <span class="eyebrow">设置与数据</span><h1>这里由你决定。</h1><p class="lead">所有开关都可以随时改变。数据也始终属于你。</p>
  <div class="setting-list">
    <button type="button" @click="toggle('low_energy_mode')"><span><strong>低能量模式</strong><small>界面只保留最轻的一步</small></span><i :class="{ on: settings.values.low_energy_mode }"></i></button>
    <button type="button" @click="toggle('auto_low_energy_mode')"><span><strong>安静简化界面</strong><small>三天没有新痕迹时自动只保留最轻的一步，不发送通知</small></span><i :class="{ on: settings.values.auto_low_energy_mode }"></i></button>
    <button type="button" @click="toggle('hide_all_numbers')"><span><strong>隐藏数字</strong><small>不显示计时与日期数字</small></span><i :class="{ on: settings.values.hide_all_numbers }"></i></button>
    <button type="button" @click="toggle('nothing_mode')"><span><strong>什么都不做模式</strong><small>不出现回顾与提示</small></span><i :class="{ on: settings.values.nothing_mode }"></i></button>
    <button type="button" @click="toggle('weekly_report_opt_out')"><span><strong>不被总结</strong><small>回看页面不生成七天整理</small></span><i :class="{ on: settings.values.weekly_report_opt_out }"></i></button>
    <button type="button" @click="toggleEcho"><span><strong>一条回声</strong><small>久未留下新痕迹时最多送回一条存在确认，默认关闭</small></span><i :class="{ on: settings.values.notify_enabled }"></i></button>
  </div>
  <div class="data-actions"><h2>带走或放下</h2><div><button type="button" @click="api.exportJson">导出 JSON</button><button type="button" @click="exportPng">导出织痕长卷</button><button type="button" @click="makeAsh">灰烬模式</button></div>
    <div v-if="purge.pending" class="purge-pending"><p>清空将在 {{ purge.grace_until ? new Date(purge.grace_until).toLocaleString('zh-CN') : '' }} 后执行。</p><button type="button" @click="cancelPurge">撤销清空</button></div>
    <button v-else class="purge-button" type="button" @click="requestPurge">清空全部数据</button>
  </div>
  <div v-if="help" class="help-card"><h2>如果你需要真正的帮助</h2><p>{{ help.note }}</p><a v-for="resource in help.resources" :key="resource.phone" :href="`tel:${resource.phone}`">{{ resource.name }} · {{ resource.phone }}</a></div>
  <p class="form-message">{{ note || settings.error }}</p>
</section></main></template>
