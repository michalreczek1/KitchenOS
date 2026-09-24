import React from "react"
import type { Metadata, Viewport } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { AnalyticsConsent } from '@/components/analytics-consent'

const _inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  metadataBase: new URL('https://kitchenos.pl'),
  title: 'KitchenOS — przepisy, plan posiłków i lista zakupów',
  description: 'Zorganizuj swoją kuchnię. Zapisuj przepisy, planuj posiłki na cały tydzień i generuj listę zakupów w KitchenOS.',
  alternates: { canonical: '/' },
  robots: { index: true, follow: true },
  openGraph: {
    type: 'website',
    locale: 'pl_PL',
    url: 'https://kitchenos.pl',
    siteName: 'KitchenOS',
    title: 'KitchenOS — Twoja kuchnia. Wreszcie ogarnięta.',
    description: 'Przepisy, plan posiłków i lista zakupów w jednym miejscu.',
  },
  icons: {
    icon: [
      {
        url: '/icon.svg',
        type: 'image/svg+xml',
      },
    ],
    apple: '/apple-icon.png',
  },
}

export const viewport: Viewport = {
  themeColor: '#1d5944',
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="pl">
      <body className={`font-sans antialiased`}>
        {children}
        <AnalyticsConsent />
      </body>
    </html>
  )
}
