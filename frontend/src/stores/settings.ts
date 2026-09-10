import { ref } from 'vue'
import { defineStore } from 'pinia'
import { api, type Settings } from '@/api'

const defaults: Settings = { low_energy_mode: false, hide_all_numbers: false, nothing_mode: false, privacy_mode: false }
export const useSettingsStore = defineStore('settings', () => {
  const values = ref<Settings>({ ...defaults })
  async function load() { values.value = await api.settings() }
  async function update(input: Partial<Settings>) { values.value = await api.updateSettings(input) }
  return { values, load, update }
})
