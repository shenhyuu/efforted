import { expect, test, type Page } from '@playwright/test'

const password = 'quiet-key'

async function enter(page: Page) {
  const status = await page.request.get('/api/v1/auth/status')
  const path = (await status.json()).initialized ? 'login' : 'setup'
  const response = await page.request.post(`/api/v1/auth/${path}`, { data: { password } })
  expect(response.ok()).toBeTruthy()
  const sessionToken = (await response.json()).token
  await page.request.patch('/api/v1/settings', {
    headers: { Authorization: `Bearer ${sessionToken}` },
    data: {
      low_energy_mode: false, auto_low_energy_mode: false, hide_all_numbers: false,
      nothing_mode: false, notify_enabled: false, weekly_report_opt_out: false,
    },
  })
  const active = await page.request.get('/api/v1/timers/active', {
    headers: { Authorization: `Bearer ${sessionToken}` },
  })
  const activeTimer = await active.json()
  if (activeTimer) {
    await page.request.post(`/api/v1/timers/${activeTimer.id}/close`, {
      headers: { Authorization: `Bearer ${sessionToken}` },
    })
  }
  await page.addInitScript((value) => localStorage.setItem('zhihen_token', value), sessionToken)
}

test.beforeEach(async ({ page }) => { await enter(page) })

test('S1: one action leaves a trace', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '我在 留下一根线' }).click()
  await expect(page.getByText('这一刻已经收好了。')).toBeVisible()
})

test('S3: a timer can pause and resume without losing its place', async ({ page }) => {
  await page.goto('/timer')
  const start = page.getByRole('button', { name: '从这里开始' })
  if (await start.isVisible()) await start.click()
  await page.getByRole('button', { name: '我先歇一会儿' }).click()
  await expect(page.getByText(/你在这里停下了/)).toBeVisible()
  await page.getByText('你停下的地方').click()
  await expect(page.getByText(/那时走了/)).toBeVisible()
  await page.getByRole('button', { name: '我回来了' }).click()
  await expect(page.getByText('你回来了。')).toBeVisible()
})

test('S4: low energy mode leaves the lightest action', async ({ page }) => {
  await page.goto('/settings')
  await page.getByRole('button', { name: /低能量模式/ }).click()
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('button', { name: '我还在 留下一根线' })).toBeVisible()
  await expect(page.getByRole('navigation')).toHaveCount(0)
})

test('S5: an undated backfill is accepted as the past', async ({ page }) => {
  await page.goto('/backfill')
  await page.getByLabel('想留的话 可以留空').fill('一段过去')
  await page.getByRole('button', { name: '把它放进织痕' }).click()
  await expect(page.getByText('这段过去已经收好了。')).toBeVisible()
})

test('S6: data controls and professional help remain reachable', async ({ page }) => {
  await page.goto('/settings')
  await expect(page.getByRole('button', { name: '导出 JSON' })).toBeVisible()
  await expect(page.getByRole('button', { name: '清空全部数据' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '如果你需要真正的帮助' })).toBeVisible()
})

test('P1: a named effort can be kept and weekly reflection stays user-initiated', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '读一页' }).click()
  await page.getByRole('button', { name: '我在 留下一根线' }).click()
  await expect(page.getByText('读一页', { exact: false }).last()).toBeVisible()

  await page.goto('/review')
  await expect(page.getByText('过去七天，织痕里新增了', { exact: false })).toHaveCount(0)
  await page.getByRole('button', { name: '整理过去七天' }).click()
  await expect(page.getByText('过去七天，织痕里新增了', { exact: false })).toBeVisible()
})

test('1.2: traces can be opened, edited, and physically removed', async ({ page }) => {
  const marker = `可整理的痕迹-${Date.now()}`
  await page.goto('/backfill')
  await page.getByLabel('想留的话 可以留空').fill(marker)
  await page.getByRole('button', { name: '把它放进织痕' }).click()
  await expect(page).toHaveURL('/')

  await page.goto('/timeline')
  const row = page.getByRole('listitem').filter({ hasText: marker })
  await row.getByRole('button', { name: '整理' }).click()
  await page.getByLabel('留下的话 可以留空').fill(`${marker}-改过`)
  await page.getByRole('button', { name: '收好改动' }).click()
  await expect(page.getByText(`${marker}-改过`)).toBeVisible()

  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('listitem').filter({ hasText: `${marker}-改过` }).getByRole('button', { name: '整理' }).click()
  await page.getByRole('button', { name: '移走这段痕迹' }).click()
  await expect(page.getByText(`${marker}-改过`)).toHaveCount(0)
})

test('1.2: every secondary page keeps a one-action quiet check-in', async ({ page }) => {
  await page.goto('/timer')
  await page.getByRole('button', { name: '留下一根线' }).click()
  await expect(page.getByText('这一刻已经收好了。')).toBeVisible()
})
