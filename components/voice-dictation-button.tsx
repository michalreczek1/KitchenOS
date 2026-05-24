'use client'

import { useRef, useState, type RefObject } from 'react'
import { Mic } from 'lucide-react'
import { cn } from '@/lib/utils'
import { insertDictationText } from '@/lib/dictation'
import { useToast } from '@/components/toast-provider'

type SpeechRecognitionAlternativeLike = {
  transcript?: string
}

type SpeechRecognitionResultLike = {
  isFinal?: boolean
  [index: number]: SpeechRecognitionAlternativeLike | undefined
}

type SpeechRecognitionResultEventLike = {
  resultIndex?: number
  results: ArrayLike<SpeechRecognitionResultLike>
}

type SpeechRecognitionErrorEventLike = {
  error?: string
}

type SpeechRecognitionLike = {
  lang: string
  continuous: boolean
  interimResults: boolean
  onstart: (() => void) | null
  onresult: ((event: SpeechRecognitionResultEventLike) => void) | null
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor
    webkitSpeechRecognition?: SpeechRecognitionConstructor
  }
}

type TextControl = HTMLInputElement | HTMLTextAreaElement

type VoiceDictationButtonProps = {
  targetRef: RefObject<TextControl | null>
  value: string
  onValueChange: (value: string) => void
  disabled?: boolean
  label?: string
  className?: string
  language?: string
}

const getRecognitionConstructor = () => {
  if (typeof window === 'undefined') return null
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null
}

const getTranscriptFromEvent = (event: SpeechRecognitionResultEventLike) => {
  let transcript = ''
  const start = Math.max(0, event.resultIndex ?? 0)
  for (let index = start; index < event.results.length; index += 1) {
    transcript += event.results[index]?.[0]?.transcript ?? ''
  }
  return transcript
}

export function VoiceDictationButton({
  targetRef,
  value,
  onValueChange,
  disabled,
  label = 'Dyktuj tekst',
  className,
  language = 'pl-PL',
}: VoiceDictationButtonProps) {
  const { showToast } = useToast()
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const stopRequestedRef = useRef(false)
  const [isListening, setIsListening] = useState(false)

  const stopListening = () => {
    stopRequestedRef.current = true
    recognitionRef.current?.stop()
    setIsListening(false)
  }

  const startListening = () => {
    const Recognition = getRecognitionConstructor()
    if (!Recognition) {
      showToast('Dyktowanie głosowe nie jest wspierane w tej przeglądarce.', 'error')
      return
    }

    const target = targetRef.current
    if (!target) return

    const baseValue = value
    const selectionStart = target.selectionStart ?? baseValue.length
    const selectionEnd = target.selectionEnd ?? selectionStart
    const recognition = new Recognition()

    stopRequestedRef.current = false
    recognition.lang = language
    recognition.continuous = false
    recognition.interimResults = true

    recognition.onstart = () => {
      setIsListening(true)
      target.focus()
    }

    recognition.onresult = (event) => {
      const transcript = getTranscriptFromEvent(event)
      const next = insertDictationText({
        value: baseValue,
        transcript,
        selectionStart,
        selectionEnd,
      })
      onValueChange(next.value)
      window.requestAnimationFrame(() => {
        target.focus()
        target.setSelectionRange(next.cursor, next.cursor)
      })
    }

    recognition.onerror = (event) => {
      if (stopRequestedRef.current) return
      const error = event.error ?? ''
      if (error === 'not-allowed' || error === 'service-not-allowed') {
        showToast('Brak dostępu do mikrofonu. Sprawdź uprawnienia strony w przeglądarce.', 'error')
        return
      }
      showToast('Nie udało się rozpocząć dyktowania. Spróbuj ponownie.', 'error')
    }

    recognition.onend = () => {
      recognitionRef.current = null
      stopRequestedRef.current = false
      setIsListening(false)
    }

    recognitionRef.current = recognition
    try {
      recognition.start()
    } catch {
      recognitionRef.current = null
      setIsListening(false)
      showToast('Nie udało się rozpocząć dyktowania. Sprawdź uprawnienia mikrofonu.', 'error')
    }
  }

  return (
    <button
      type="button"
      aria-label={isListening ? 'Zatrzymaj dyktowanie' : label}
      aria-pressed={isListening}
      title={isListening ? 'Zatrzymaj dyktowanie' : label}
      disabled={disabled && !isListening}
      onClick={isListening ? stopListening : startListening}
      className={cn(
        'inline-flex h-11 w-11 items-center justify-center rounded-xl border border-border/60 bg-card/90 text-muted-foreground shadow-sm transition-all hover:border-primary/50 hover:text-primary focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:pointer-events-none disabled:opacity-50',
        isListening && 'border-primary bg-primary/10 text-primary ring-2 ring-primary/25',
        className,
      )}
    >
      <Mic className={cn('h-4 w-4', isListening && 'animate-pulse')} />
    </button>
  )
}
