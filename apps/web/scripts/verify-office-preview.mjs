// Focused visual check. Start Vite, then run with Playwright available via
// PLAYWRIGHT_MODULE (absolute package index.js) or installed locally.
import { createRequire } from 'node:module'
import { mkdir, writeFile } from 'node:fs/promises'
import assert from 'node:assert/strict'
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const base = process.env.OFFICE_URL || 'http://127.0.0.1:5173'
const output = new URL('../../../docs/office-rebuild-evidence/', import.meta.url)
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const errors = []
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
  page.on('pageerror', (e) => errors.push(e.message))
  await page.clock.install()
  await page.goto(`${base}/development-floor.html`)
  await page.getByRole('button', { name: 'Try demo fixtures' }).click()
  await page.clock.runFor(32)
  for (const [width, height] of [[1280, 720], [1440, 900], [1920, 1080]]) {
    await page.setViewportSize({ width, height })
    await page.clock.runFor(64)
    await page.screenshot({ path: new URL(`preview-${width}x${height}.png`, output).pathname })
    const buttons = await page.getByRole('button').evaluateAll((nodes) => nodes.map((n) => {
      const r = n.getBoundingClientRect(); return { x: r.x, y: r.y, right: r.right, bottom: r.bottom }
    }))
    assert(buttons.every((r) => r.x >= 0 && r.y >= 0 && r.right <= width && r.bottom <= height), 'offscreen controls')
  }
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.getByRole('button', { name: 'Jordan · blocked' }).focus()
  await page.keyboard.press('Enter')
  assert.equal(await page.getByRole('button', { name: 'Jordan · blocked' }).getAttribute('aria-pressed'), 'true')
  await page.screenshot({ path: new URL('selected-blocked.png', output).pathname })
  await page.getByRole('button', { name: 'Preview walk' }).click()
  for (const [name, ms] of [['behind-desk', 8000], ['front-aisle', 10000], ['doorway', 15000]]) {
    await page.clock.runFor(ms)
    await page.screenshot({ path: new URL(`${name}.png`, output).pathname })
  }
  await page.clock.resume()
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.waitForFunction(() => document.querySelector('button[aria-pressed][disabled]'), null, { polling: 100 })
  assert(await page.getByRole('button', { name: 'Seat employee' }).isDisabled())
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.waitForFunction(() => !document.querySelector('button[aria-pressed][disabled]'), null, { polling: 100 })
  await page.getByRole('button', { name: 'Use live state' }).click()
  await page.getByRole('status').filter({ hasText: 'Waiting for employee telemetry' }).waitFor()

  // Inject a snapshot through the same store boundary as live telemetry.
  await page.evaluate(async () => {
    const { useSim } = await import('/src/stores/simStore.ts')
    const avatar = { employee_id: 'visual-check', name: 'Live employee', role: 'Engineer', team: 'Dev', sprite_key: '', tile: { x: 0, y: 0 }, facing: 's', fsm: 'working', badge: 'working', risk_score: 0, status: 'active', current_task_title: 'Snapshot fixture' }
    useSim.setState({ avatars: { 'visual-check': avatar } })
  })
  await page.getByRole('button', { name: 'Live · working' }).waitFor()
  await page.evaluate(async () => {
    const { useSim } = await import('/src/stores/simStore.ts')
    useSim.setState((s) => ({ avatars: { 'visual-check': { ...s.avatars['visual-check'], fsm: 'blocked', badge: 'blocked' } } }))
  })
  await page.getByRole('button', { name: 'Live · blocked' }).waitFor()
  await page.evaluate(async () => {
    const { useSim } = await import('/src/stores/simStore.ts')
    useSim.setState({ avatars: {} })
  })
  await page.getByRole('status').filter({ hasText: 'Waiting for employee telemetry' }).waitFor()

  await page.goto(`${base}/office?scene=development`)
  await page.getByRole('button', { name: 'Try demo fixtures' }).click()
  await page.waitForTimeout(100)
  await page.screenshot({ path: new URL('preview-route.png', output).pathname })
  await page.getByRole('button', { name: 'Current office', exact: true }).click()
  await page.getByLabel('Interactive live office simulation').waitFor()
  assert.deepEqual(errors, [])
  await writeFile(new URL('browser-check.json', output), JSON.stringify({
    viewports: ['1280x720', '1440x900', '1920x1080'],
    passed: ['fixture states', 'keyboard selection', 'viewport controls', 'movement snapshots', 'reduced motion', 'snapshot additions/transitions/removals', 'route preview/rollback'],
    pageErrors: errors,
    performance: 'No sustained frame timing or memory measurement; no 60fps claim.',
  }, null, 2) + '\n')
  console.log('Office preview browser checks passed; evidence saved in docs/office-rebuild-evidence.')
} finally { await browser.close() }
