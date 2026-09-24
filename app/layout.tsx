import React from "react"
import type { Metadata, Viewport } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'

const _inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: 'KitchenOS — przepisy, plan posiłków i lista zakupów',
  description: 'Zorganizuj swoją kuchnię. Zapisuj przepisy, planuj posiłki na cały tydzień i generuj listę zakupów w KitchenOS.',
  generator: 'v0.app',
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
      </body>
    </html>
  )
}
