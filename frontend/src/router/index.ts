import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '@/views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/backfill', name: 'backfill', component: () => import('@/views/BackfillView.vue') },
    { path: '/timer', name: 'timer', component: () => import('@/views/TimerView.vue') },
    { path: '/lamps', name: 'lamps', component: () => import('@/views/LampsView.vue') },
    { path: '/settings', name: 'settings', component: () => import('@/views/SettingsView.vue') },
  ],
})

export default router
