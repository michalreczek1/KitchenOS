import { expect, test, type Page, type APIRequestContext } from '@playwright/test'

const API_URL = 'http://127.0.0.1:8000'
const BOOTSTRAP_TOKEN = 'kitchenos-e2e-bootstrap-token'
const E2E_EMAIL = 'dictation-e2e@example.com'
const E2E_PASSWORD = 'Password123!'

async function authenticate(page: Page, request: APIRequestContext) {
  await request.post(`${API_URL}/api/auth/bootstrap`, {
    data: { email: E2E_EMAIL, password: E2E_PASSWORD, token: BOOTSTRAP_TOKEN },
  })

  const loginResponse = await request.post(`${API_URL}/api/auth/login`, {
    data: { email: E2E_EMAIL, password: E2E_PASSWORD },
  })
  expect(loginResponse.ok()).toBeTruthy()
  const loginBody = (await loginResponse.json()) as { access_token: string }

  await page.addInitScript((token) => {
    window.localStorage.setItem('kitchenOS_token', token)
  }, loginBody.access_token)
}

async function installSpeechRecognitionMock(page: Page, options?: { error?: string }) {
  await page.addInitScript((mockOptions) => {
    ;(window as any).__speechMock = {
      transcript: '',
      error: mockOptions?.error ?? null,
    }

    class MockSpeechRecognition {
      lang = ''
      continuous = true
      interimResults = false
      onstart: (() => void) | null = null
      onresult: ((event: unknown) => void) | null = null
      onerror: ((event: unknown) => void) | null = null
      onend: (() => void) | null = null

      start() {
        this.onstart?.()
        window.setTimeout(() => {
          const speechMock = (window as any).__speechMock
          if (speechMock.error) {
            this.onerror?.({ error: speechMock.error })
            this.onend?.()
            return
          }
          this.onresult?.({
            resultIndex: 0,
            results: [
              {
                0: { transcript: speechMock.transcript },
                isFinal: true,
              },
            ],
          })
          this.onend?.()
        }, 0)
      }

      stop() {
        this.onend?.()
      }
    }

    ;(window as any).SpeechRecognition = MockSpeechRecognition
    ;(window as any).webkitSpeechRecognition = MockSpeechRecognition
  }, options ?? {})
}

async function setTranscript(page: Page, transcript: string) {
  await page.evaluate((value) => {
    ;(window as any).__speechMock.transcript = value
  }, transcript)
}

async function openManualAddRecipe(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: 'Dodaj', exact: true }).click()
  await page.getByRole('button', { name: 'Recznie', exact: true }).click()
}

test('dictates into a text input', async ({ page, request }) => {
  await authenticate(page, request)
  await installSpeechRecognitionMock(page)
  await openManualAddRecipe(page)
  await setTranscript(page, 'zupa krem z dyni')

  await page.getByRole('button', { name: 'Dyktuj nazwę przepisu' }).click()

  await expect(page.getByPlaceholder('np. Spaghetti Bolognese')).toHaveValue('zupa krem z dyni')
})

test('dictates into a textarea', async ({ page, request }) => {
  await authenticate(page, request)
  await installSpeechRecognitionMock(page)
  await openManualAddRecipe(page)
  await setTranscript(page, 'gotuj przez dziesięć minut')

  await page.getByRole('button', { name: 'Dyktuj instrukcje przygotowania' }).click()

  await expect(page.getByPlaceholder('Opisz sposob przygotowania...')).toHaveValue('gotuj przez dziesięć minut')
})

test('keeps dictation usable on mobile', async ({ page, request }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await authenticate(page, request)
  await installSpeechRecognitionMock(page)
  await openManualAddRecipe(page)
  await setTranscript(page, 'naleśniki')

  const microphone = page.getByRole('button', { name: 'Dyktuj nazwę przepisu' })
  const box = await microphone.boundingBox()
  expect(box?.width).toBeGreaterThanOrEqual(40)
  expect(box?.height).toBeGreaterThanOrEqual(40)

  await microphone.click()
  await expect(page.getByPlaceholder('np. Spaghetti Bolognese')).toHaveValue('naleśniki')
})

test('shows a clear message when SpeechRecognition is not supported', async ({ page, request }) => {
  await authenticate(page, request)
  await page.addInitScript(() => {
    Object.defineProperty(window, 'SpeechRecognition', {
      configurable: true,
      value: undefined,
    })
    Object.defineProperty(window, 'webkitSpeechRecognition', {
      configurable: true,
      value: undefined,
    })
  })
  await openManualAddRecipe(page)

  await page.getByRole('button', { name: 'Dyktuj nazwę przepisu' }).click()

  await expect(page.getByText('Dyktowanie głosowe nie jest wspierane w tej przeglądarce.')).toBeVisible()
})

test('shows a permission message when microphone access is denied', async ({ page, request }) => {
  await authenticate(page, request)
  await installSpeechRecognitionMock(page, { error: 'not-allowed' })
  await openManualAddRecipe(page)

  await page.getByRole('button', { name: 'Dyktuj nazwę przepisu' }).click()

  await expect(page.getByText('Brak dostępu do mikrofonu. Sprawdź uprawnienia strony w przeglądarce.')).toBeVisible()
})
