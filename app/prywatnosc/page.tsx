import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Prywatność — KitchenOS',
  description: 'Informacje o opcjonalnym pomiarze Google Analytics w KitchenOS.',
  alternates: { canonical: '/prywatnosc' },
}

export default function PrivacyPage() {
  return <main className="privacy-page">
    <a href="/">← KitchenOS</a>
    <h1>Prywatność</h1>
    <h2>Google Analytics</h2>
    <p>Po Twojej zgodzie używamy Google Analytics 4 do pomiaru odwiedzin, źródeł ruchu i ogólnego sposobu korzystania z KitchenOS. Identyfikator pomiaru: G-QCNWMQRMFD. Nie przekazujemy Google treści przepisów, nazwisk ani adresów e-mail.</p>
    <p>Google może zapisywać pliki cookie, w tym _ga, oraz przetwarzać dane techniczne przeglądarki. <a href="https://policies.google.com/technologies/partner-sites" target="_blank" rel="noreferrer">Dowiedz się, jak Google wykorzystuje dane z witryn</a>.</p>
    <p>Pomiar nie włącza się przed wyrażeniem zgody. Zgodę możesz zmienić poniżej. Jej wycofanie wyłącza pomiar i usuwa pliki cookie Analytics dostępne dla KitchenOS.</p>
    <a href="/prywatnosc?analytics=1">Zmień ustawienia analityki</a>
  </main>
}
