import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api, type Settings } from '@/api'

const defaults: Settings = { low_energy_mode: false, hide_all_numbers: false, nothing_mode: false, privacy_mode: false }
export const useSettingsStore = defineStore('settings', () => {
  const values = ref<Settings>({ ...defaults })
  const error = ref<string | null>(null)
  async function load() {
    try { values.value = await api.settings(); error.value = null }
    catch (reason) { error.value = reason instanceof Error ? reason.message : '设置暂时没有回应。' }
  }
  async function update(input: Partial<Settings>) {
    try { values.value = await api.updateSettings(input); error.value = null; return true }
    catch (reason) { error.value = reason instanceof Error ? reason.message : '设置暂时没有回应。'; return false }
  }
  return { values, error, load, update }
})
