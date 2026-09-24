import { test, expect } from '@playwright/test'

test('landing działa na desktopie i telefonie', async ({ browser }) => {
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
