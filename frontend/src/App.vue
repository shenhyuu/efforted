<script setup lang="ts">
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import AuthView from '@/views/AuthView.vue'
import QuietCheckin from '@/components/QuietCheckin.vue'
import { useSessionStore } from '@/stores/session'
import { useSettingsStore } from '@/stores/settings'

const navigation = [
  { to: '/', label: '织痕', short: '今日', icon: '∿' },
  { to: '/timeline', label: '痕迹', short: '痕迹', icon: '≀' },
  { to: '/backfill', label: '补记', short: '补记', icon: '↶' },
  { to: '/timer', label: '计时', short: '计时', icon: '◷' },
  { to: '/lamps', label: '一盏灯', short: '留灯', icon: '◇' },
  { to: '/review', label: '回看', short: '回看', icon: '≋' },
  { to: '/settings', label: '设置', short: '设置', icon: '·' },
]

const session = useSessionStore()
const settings = useSettingsStore()
const router = useRouter()
onMounted(async () => {
  window.addEventListener('zhihen-auth-expired', session.expire)
  await session.bootstrap()
  if (session.authenticated) await settings.load()
})
onBeforeUnmount(() => window.removeEventListener('zhihen-auth-expired', session.expire))
watch(() => session.authenticated, async (value) => { if (value) await settings.load() })
watch(() => settings.lowEnergyActive, async (value) => {
  if (value && router.currentRoute.value.path !== '/') await router.push('/')
})
async function leave() { await session.leave(); await router.push('/') }
</script>

<template>
  <div v-if="!session.ready" class="page-loading">正在轻轻展开。</div>
  <AuthView v-else-if="!session.authenticated" />
  <div v-else :class="['app-shell', { 'lite-shell': settings.lowEnergyActive }]">
    <div class="ambient ambient-one" aria-hidden="true"></div>
    <div class="ambient ambient-two" aria-hidden="true"></div>
    <header class="site-header">
      <RouterLink class="brand" to="/" aria-label="回到织痕首页">
        <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>
        <span class="brand-copy"><strong>织痕</strong><small>ZHĪ HÉN</small></span>
      </RouterLink>
      <nav v-if="!settings.lowEnergyActive" aria-label="主要页面">
        <RouterLink v-for="item in navigation" :key="item.to" :to="item.to">
          <span class="nav-icon" aria-hidden="true">{{ item.icon }}</span>
          <span class="nav-label">{{ item.label }}</span>
          <span class="nav-short">{{ item.short }}</span>
        </RouterLink>
      </nav>
      <button v-else class="text-button" type="button" @click="settings.showFullInterface">回到完整界面</button>
    </header>
    <RouterView />
    <QuietCheckin v-if="!settings.lowEnergyActive && router.currentRoute.value.path !== '/'" />
    <footer v-if="!settings.lowEnergyActive" class="site-footer">
      <span>不评判每一次出现</span>
      <button class="logout-button" type="button" @click="leave">安静离开</button>
    </footer>
  </div>
</template>
