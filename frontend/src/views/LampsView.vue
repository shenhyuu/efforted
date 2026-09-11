<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type Energy, type Lamp } from '@/api'

const lamps = ref<Lamp[]>([]), message = ref(''), energy = ref<Energy | undefined>(), opened = ref<Lamp | null>(null), note = ref('')
async function load() { try { lamps.value = (await api.lamps()).lamps } catch (reason) { note.value = reason instanceof Error ? reason.message : '灯暂时没有回应。' } }
async function create() {
  if (!message.value.trim()) return
  try { const lamp = await api.createLamp(message.value.trim(), energy.value); lamps.value.unshift(lamp); message.value = ''; energy.value = undefined; note.value = lamp.pending ? '这盏灯会在恢复联结后留在这里。' : '这盏灯留在这里了。' }
  catch (reason) { note.value = reason instanceof Error ? reason.message : '这盏灯暂时没有被收好。' }
}
async function open(lamp: Lamp) {
  if (lamp.pending) { note.value = '这盏灯会在恢复联结后留在这里。'; return }
  try { opened.value = await api.openLamp(lamp.id) } catch (reason) { note.value = reason instanceof Error ? reason.message : '这盏灯暂时没有回应。' }
}
async function remove(lamp: Lamp) {
  if (!window.confirm('这盏灯会被立即物理删除。确认继续吗？')) return
  try { await api.deleteLamp(lamp.id); lamps.value = lamps.value.filter((item) => item.id !== lamp.id); opened.value = null; note.value = '这盏灯已经移走。' }
  catch (reason) { note.value = reason instanceof Error ? reason.message : '这盏灯暂时没有回应。' }
}
onMounted(load)
</script>

<template><main class="single-page"><section class="lamp-card">
  <span class="eyebrow">留一盏灯</span><h1>写给未来的自己。</h1><p class="lead">它不会主动出现，只在你来到这里时被打开。</p>
  <div v-if="opened" class="opened-lamp"><span>那时留下的话</span><blockquote>{{ opened.message }}</blockquote>
    <p class="lamp-context">{{ opened.energy_at_write ? '写下它的时候，你也记录了自己的电量。它一直在。' : '写下它的时候，这句话被留在了这里。' }}</p>
    <div><button class="text-button" type="button" @click="opened = null">轻轻合上</button><button class="delete-action" type="button" @click="remove(opened)">移走这盏灯</button></div>
  </div>
  <template v-else><form class="lamp-form" @submit.prevent="create"><label>想留下的话<textarea v-model="message" maxlength="1000" rows="3" required></textarea></label>
    <div class="choice-row"><button v-for="item in [{v:'low',l:'低'},{v:'mid',l:'中'},{v:'enough',l:'够用'}]" :key="item.v" type="button" :class="{ selected: energy === item.v }" @click="energy = item.v as Energy">{{ item.l }}</button></div>
    <button class="primary-action" type="submit">留在这里</button></form>
    <div class="lamp-shelf"><p v-if="!lamps.length">还没有留下灯，也很好。</p><button v-for="lamp in lamps" :key="lamp.id" class="lamp-item" type="button" @click="open(lamp)"><span class="lamp-flame"></span><small>{{ lamp.pending ? '等待联结' : new Date(lamp.created_at).toLocaleDateString('zh-CN') }}</small><strong>{{ lamp.pending ? '会留在这里' : '当你想打开时' }}</strong></button></div>
  </template><p class="form-message">{{ note }}</p>
</section></main></template>
