import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api, token } from '@/api'

export const useSessionStore = defineStore('session', () => {
  const ready = ref(false)
  const initialized = ref(false)
  const authenticated = ref(Boolean(token.get()))
  const error = ref<string | null>(null)

  async function bootstrap() {
    try {
      initialized.value = (await api.authStatus()).initialized
      authenticated.value = Boolean(token.get())
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : '这里暂时没有回应。'
    } finally { ready.value = true }
  }
  async function enter(password: string) {
    error.value = null
    try {
      const result = initialized.value ? await api.login(password) : await api.setup(password)
      token.set(result.token); authenticated.value = true; initialized.value = true
      return true
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : '这个密码没有对上。'
      return false
    }
  }
  async function leave() {
    try { await api.logout() } finally { token.clear(); authenticated.value = false }
  }
  function expire() { token.clear(); authenticated.value = false }
  return { ready, initialized, authenticated, error, bootstrap, enter, leave, expire }
})
