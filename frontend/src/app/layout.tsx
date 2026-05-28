import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'ReplyOS - AI WhatsApp Platform',
  description: 'AI-Powered WhatsApp Marketing & Multi-Agent SaaS Platform',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-background text-slate-100 min-h-screen">
        {children}
      </body>
    </html>
  )
}
