<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import AuthView from '@/views/AuthView.vue'
import { useSessionStore } from '@/stores/session'
import { useSettingsStore } from '@/stores/settings'

const session = useSessionStore()
const settings = useSettingsStore()
const router = useRouter()
onMounted(async () => {
  window.addEventListener('zhihen-auth-expired', session.expire)
  await session.bootstrap()
  if (session.authenticated) await settings.load()
})
watch(() => session.authenticated, async (value) => { if (value) await settings.load() })
async function leave() { await session.leave(); await router.push('/') }
</script>

<template>
  <div v-if="!session.ready" class="page-loading">正在轻轻展开。</div>
  <AuthView v-else-if="!session.authenticated" />
  <div v-else :class="['app-shell', { 'lite-shell': settings.values.low_energy_mode }]">
    <header class="site-header">
      <RouterLink class="brand" to="/" aria-label="回到织痕首页">
        <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>
        <span>织痕</span>
      </RouterLink>
      <nav v-if="!settings.values.low_energy_mode" aria-label="主要页面">
        <RouterLink to="/">织痕</RouterLink><RouterLink to="/backfill">补记</RouterLink>
        <RouterLink to="/timer">计时</RouterLink><RouterLink to="/lamps">一盏灯</RouterLink>
        <RouterLink to="/settings">设置</RouterLink>
      </nav>
      <button v-else class="text-button" type="button" @click="settings.update({ low_energy_mode: false })">回到完整界面</button>
    </header>
    <RouterView />
    <button v-if="!settings.values.low_energy_mode" class="logout-button" type="button" @click="leave">离开</button>
  </div>
</template>
