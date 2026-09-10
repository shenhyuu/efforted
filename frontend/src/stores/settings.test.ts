import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { api, type Settings } from '@/api'
import { useSettingsStore } from './settings'

const automatic: Settings = {
  low_energy_mode: false,
  auto_low_energy_mode: true,
  auto_low_energy_active: true,
  hide_all_numbers: false,
  nothing_mode: false,
  notify_enabled: false,
  weekly_report_opt_out: false,
  privacy_mode: false,
}

describe('low energy settings', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('allows automatic simplification to be dismissed without disabling the preference', async () => {
    vi.spyOn(api, 'settings').mockResolvedValue({ ...automatic })
    const store = useSettingsStore()
    await store.load()

    expect(store.lowEnergyActive).toBe(true)
    await store.showFullInterface()

    expect(store.lowEnergyActive).toBe(false)
    expect(store.values.auto_low_energy_mode).toBe(true)
  })

  it('leaves automatic simplification after a new activity', async () => {
    vi.spyOn(api, 'settings').mockResolvedValue({ ...automatic })
    const store = useSettingsStore()
    await store.load()
    store.acknowledgeActivity()

    expect(store.lowEnergyActive).toBe(false)
    expect(store.values.auto_low_energy_active).toBe(false)
  })
})
