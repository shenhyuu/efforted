<script setup lang="ts">
import { ref } from 'vue'
import { api } from '@/api'
import { useSettingsStore } from '@/stores/settings'

const settings = useSettingsStore()
const lines = ref<string[]>([])
const busy = ref(false)
const message = ref('')

async function generate() {
  if (busy.value) return
  busy.value = true
  message.value = ''
  try { lines.value = (await api.weeklyReflection()).lines }
  catch (reason) { message.value = reason instanceof Error ? reason.message : '这次回看暂时没有展开。' }
  finally { busy.value = false }
}
</script>

<template>
  <main class="single-page"><section class="form-card reflection-card">
    <span class="eyebrow">主动回看</span><h1>只整理已经发生的事。</h1>
    <p class="lead">这份回看只在你点击后生成，只复述过去七天留在织痕里的事实。</p>
    <p v-if="settings.values.weekly_report_opt_out" class="quiet-panel">这里按你的选择保持安静。可以在设置里重新打开。</p>
    <button v-else class="primary-action" type="button" :disabled="busy" @click="generate">
      {{ busy ? '正在整理' : '整理过去七天' }}
    </button>
    <div v-if="lines.length" class="reflection-lines" aria-live="polite">
      <p v-for="line in lines" :key="line">{{ line }}</p>
    </div>
    <p class="form-message" role="status">{{ message }}</p>
  </section></main>
</template>
