import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api, type Settings, type SettingsUpdate } from '@/api'

const defaults: Settings = {
  low_energy_mode: false, auto_low_energy_mode: false, auto_low_energy_active: false,
  hide_all_numbers: false, nothing_mode: false, notify_enabled: false,
  weekly_report_opt_out: false, privacy_mode: false,
}
export const useSettingsStore = defineStore('settings', () => {
  const values = ref<Settings>({ ...defaults })
  const automaticSimplificationDismissed = ref(false)
  const lowEnergyActive = computed(
    () => values.value.low_energy_mode
      || (values.value.auto_low_energy_active && !automaticSimplificationDismissed.value),
  )
  const error = ref<string | null>(null)
  function receive(next: Settings) {
    values.value = next
    if (!next.auto_low_energy_active) automaticSimplificationDismissed.value = false
  }
  async function load() {
    try { receive(await api.settings()); error.value = null }
    catch (reason) { error.value = reason instanceof Error ? reason.message : '设置暂时没有回应。' }
  }
  async function update(input: SettingsUpdate) {
    try { receive(await api.updateSettings(input)); error.value = null; return true }
    catch (reason) { error.value = reason instanceof Error ? reason.message : '设置暂时没有回应。'; return false }
  }
  async function showFullInterface() {
    const updated = values.value.low_energy_mode
      ? await update({ low_energy_mode: false })
      : true
    if (updated && values.value.auto_low_energy_active) {
      automaticSimplificationDismissed.value = true
    }
    return updated
  }
  function acknowledgeActivity() {
    values.value.auto_low_energy_active = false
    automaticSimplificationDismissed.value = false
  }
  return { values, lowEnergyActive, error, load, update, showFullInterface, acknowledgeActivity }
})
