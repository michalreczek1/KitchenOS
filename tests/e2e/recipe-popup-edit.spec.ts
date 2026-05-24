import { expect, test } from '@playwright/test'

const API_URL = 'http://127.0.0.1:8000'
const BOOTSTRAP_TOKEN = 'kitchenos-e2e-bootstrap-token'
const E2E_EMAIL = 'dictation-e2e@example.com'
const E2E_PASSWORD = 'Password123!'

test('edits recipe ingredients inside popup and persists recalculated recipe', async ({ page, request }) => {
  await request.post(`${API_URL}/api/auth/bootstrap`, {
    data: { email: E2E_EMAIL, password: E2E_PASSWORD, token: BOOTSTRAP_TOKEN },
  })

  const loginResponse = await request.post(`${API_URL}/api/auth/login`, {
    data: { email: E2E_EMAIL, password: E2E_PASSWORD },
  })
  expect(loginResponse.ok()).toBeTruthy()
  const loginBody = (await loginResponse.json()) as { access_token: string }
  const token = loginBody.access_token
  expect(token).toBeTruthy()

  const createRecipeResponse = await request.post(`${API_URL}/api/recipes`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    data: {
      title: 'E2E Makaron',
      ingredients: [
        { item: 'makaron', amount: '200 g' },
        { item: 'ser', amount: '100 g' },
      ],
      instructions: ['Ugotuj makaron.', 'Wymieszaj z serem.'],
      base_portions: 2,
      declared_category: 'obiady',
    },
  })
  expect(createRecipeResponse.ok()).toBeTruthy()
  const createdRecipe = (await createRecipeResponse.json()) as { id: number; title: string }

  await page.addInitScript((authToken) => {
    window.localStorage.setItem('kitchenOS_token', authToken)
  }, token)

  await page.goto('/')
  await page.getByRole('button', { name: 'Przepisy' }).click()
  await expect(page.getByText('E2E Makaron')).toBeVisible()

  await page.getByTitle('Podgląd przepisu').click()
  await expect(page.locator('h2', { hasText: 'E2E Makaron' })).toBeVisible()
  await page.getByRole('button', { name: 'Edytuj składniki' }).click()

  await page.getByLabel('Ilość składnika 1').fill('300 g')
  await page.getByLabel('Nazwa składnika 1').fill('makaron pelnoziarnisty')
  await page.getByRole('button', { name: 'Dodaj składnik' }).click()
  await page.getByLabel('Ilość składnika 3').fill('2 szt')
  await page.getByLabel('Nazwa składnika 3').fill('pomidory')
  await page.getByLabel('Usuń składnik 2').click()
  await page.getByRole('button', { name: 'Zapisz i przelicz' }).click()

  await expect(page.getByText('300 g makaron pelnoziarnisty')).toBeVisible()
  await expect(page.getByText('2 szt pomidory')).toBeVisible()
  await expect(page.getByText('100 g ser')).not.toBeVisible()

  await page.keyboard.press('Escape')
  await page.getByTitle('Podgląd przepisu').click()
  await expect(page.getByText('300 g makaron pelnoziarnisty')).toBeVisible()
  await expect(page.getByText('2 szt pomidory')).toBeVisible()

  const updatedRecipeResponse = await request.get(`${API_URL}/api/recipes/${createdRecipe.id}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })
  expect(updatedRecipeResponse.ok()).toBeTruthy()
  const updatedRecipe = (await updatedRecipeResponse.json()) as {
    ingredients: string[]
    ingredients_customized: boolean
    nutrition_calories_kcal?: number | null
  }

  expect(updatedRecipe.ingredients_customized).toBe(true)
  expect(updatedRecipe.ingredients).toEqual(['300 g makaron pelnoziarnisty', '2 szt pomidory'])
  expect(updatedRecipe.nutrition_calories_kcal).not.toBeNull()
})
