'use client'

import { useEffect, useState } from 'react'
import Script from 'next/script'

const STORAGE_KEY = 'kitchenos.analyticsConsent.v1'
const GA_ID = 'G-QCNWMQRMFD'

export function AnalyticsConsent() {
  const [decision, setDecision] = useState<'pending' | 'granted' | 'denied' | null>(null)

  useEffect(() => {
    if (new URLSearchParams(window.location.search).has('analytics')) {
      setDecision('pending')
      return
    }
    const saved = localStorage.getItem(STORAGE_KEY)
    setDecision(saved === 'granted' || saved === 'denied' ? saved : 'pending')
  }, [])

  function decide(allow: boolean) {
    const next = allow ? 'granted' : 'denied'
    localStorage.setItem(STORAGE_KEY, next)
    setDecision(next)
    if (window.location.search.includes('analytics=')) window.history.replaceState(null, '', window.location.pathname)
    if (!allow) {
      for (const cookie of document.cookie.split(';')) {
        const name = cookie.split('=')[0]?.trim()
        if (!name?.startsWith('_ga')) continue
        document.cookie = `${name}=; Max-Age=0; Path=/; SameSite=Lax`
        document.cookie = `${name}=; Max-Age=0; Path=/; Domain=.kitchenos.pl; SameSite=Lax`
      }
      if (decision === 'granted') window.location.reload()
    }
  }

  return <>
    {decision === 'granted' && <>
      <Script src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`} strategy="afterInteractive" />
      <Script id="kitchenos-google-analytics" strategy="afterInteractive">
        {`window.dataLayer=window.dataLayer||[];window.gtag=function(){dataLayer.push(arguments)};gtag('js',new Date());gtag('config','${GA_ID}');`}
      </Script>
    </>}
    {decision === 'pending' && <aside className="analytics-consent" aria-label="Zgoda na analitykę">
      <div><strong>Pomóż ulepszać KitchenOS</strong><p>Za Twoją zgodą użyjemy Google Analytics do pomiaru ruchu i korzystania ze strony. <a href="/prywatnosc">Więcej o prywatności</a>.</p></div>
      <div className="analytics-consent-actions">
        <button type="button" onClick={() => decide(false)}>Nie, dziękuję</button>
        <button type="button" onClick={() => decide(true)}>Zgadzam się</button>
      </div>
    </aside>}
  </>
}
