'use client'

import React, { useRef } from 'react'
import { cn } from '@/lib/utils'
import { VoiceDictationButton } from '@/components/voice-dictation-button'

type DictationInputProps = Omit<React.ComponentProps<'input'>, 'value' | 'onChange'> & {
  value: string
  onValueChange: (value: string) => void
  dictationLabel: string
  wrapperClassName?: string
  leadingIcon?: React.ReactNode
}

export function DictationInput({
  value,
  onValueChange,
  dictationLabel,
  wrapperClassName,
  leadingIcon,
  className,
  disabled,
  type = 'text',
  ...props
}: DictationInputProps) {
  const inputRef = useRef<HTMLInputElement | null>(null)

  return (
    <div className={cn('relative', wrapperClassName)}>
      {leadingIcon}
      <input
        ref={inputRef}
        type={type}
        value={value}
        onChange={(event) => onValueChange(event.target.value)}
        disabled={disabled}
        className={cn(className, 'pr-14')}
        {...props}
      />
      <VoiceDictationButton
        targetRef={inputRef}
        value={value}
        onValueChange={onValueChange}
        disabled={disabled}
        label={dictationLabel}
        className="absolute right-2 top-1/2 -translate-y-1/2"
      />
    </div>
  )
}

type DictationTextareaProps = Omit<React.ComponentProps<'textarea'>, 'value' | 'onChange'> & {
  value: string
  onValueChange: (value: string) => void
  dictationLabel: string
  wrapperClassName?: string
}

export function DictationTextarea({
  value,
  onValueChange,
  dictationLabel,
  wrapperClassName,
  className,
  disabled,
  ...props
}: DictationTextareaProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  return (
    <div className={cn('relative', wrapperClassName)}>
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(event) => onValueChange(event.target.value)}
        disabled={disabled}
        className={cn(className, 'pr-14')}
        {...props}
      />
      <VoiceDictationButton
        targetRef={textareaRef}
        value={value}
        onValueChange={onValueChange}
        disabled={disabled}
        label={dictationLabel}
        className="absolute right-2 top-2"
      />
    </div>
  )
}
