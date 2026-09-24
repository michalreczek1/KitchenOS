import { test, expect } from '@playwright/test'

test('landing działa na desktopie i telefonie', async ({ browser, request }) => {
  const html = await (await request.get('/')).text()
  expect(html).toContain('Twoja kuchnia')
  expect(html).toContain('<link rel="canonical" href="https://kitchenos.pl"')
  expect((await request.get('/robots.txt')).ok()).toBeTruthy()
  expect((await request.get('/sitemap.xml')).ok()).toBeTruthy()
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport })
    await page.goto('/')
    await expect(page.getByRole('heading', { name: /Twoja kuchnia/ })).toBeVisible()
    await expect(page.getByRole('link', { name: /Otwórz KitchenOS/ })).toHaveAttribute('href', '/?login=1')
    await expect(page.locator('#faq details')).toHaveCount(4)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy()
    await page.screenshot({ path: `test-results/landing-${viewport.width}.png`, fullPage: true })
    await page.getByRole('link', { name: /Otwórz KitchenOS/ }).click()
    await expect(page.getByText('Zaloguj się', { exact: false }).first()).toBeVisible()
    await page.close()
  }
})

test('Google Analytics działa dopiero po zgodzie i można ją wycofać', async ({ page }) => {
  const requests: string[] = []
  await page.route(/googletagmanager\.com|google-analytics\.com/, async route => {
    requests.push(route.request().url())
    await route.abort()
  })
  await page.goto('/')
  const banner = page.getByRole('complementary', { name: 'Zgoda na analitykę' })
  await expect(banner).toBeVisible()
  expect(requests).toEqual([])
  await banner.getByRole('button', { name: 'Zgadzam się' }).click()
  await expect(banner).toBeHidden()
  await expect.poll(() => requests.some(url => url.includes('G-QCNWMQRMFD'))).toBeTruthy()
  await page.goto('/prywatnosc')
  await page.getByRole('link', { name: 'Zmień ustawienia analityki' }).click()
  await expect(banner).toBeVisible()
  await banner.getByRole('button', { name: 'Nie, dziękuję' }).click()
  await expect(banner).toBeHidden()
  expect(await page.evaluate(() => localStorage.getItem('kitchenos.analyticsConsent.v1'))).toBe('denied')
})
