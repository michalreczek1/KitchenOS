import { describe, expect, it } from 'vitest'
import { insertDictationText } from '../lib/dictation'

describe('insertDictationText', () => {
  it('fills an empty field', () => {
    expect(
      insertDictationText({
        value: '',
        transcript: ' zupa pomidorowa ',
        selectionStart: 0,
        selectionEnd: 0,
      })
    ).toEqual({ value: 'zupa pomidorowa', cursor: 15 })
  })

  it('appends at the end with a space', () => {
    expect(
      insertDictationText({
        value: 'Makaron',
        transcript: 'z sosem',
        selectionStart: 7,
        selectionEnd: 7,
      })
    ).toEqual({ value: 'Makaron z sosem', cursor: 15 })
  })

  it('inserts in the middle without losing surrounding text', () => {
    expect(
      insertDictationText({
        value: 'Ala kota',
        transcript: 'ma',
        selectionStart: 4,
        selectionEnd: 4,
      })
    ).toEqual({ value: 'Ala ma kota', cursor: 6 })
  })

  it('replaces selected text', () => {
    expect(
      insertDictationText({
        value: 'Dodaj stary tekst',
        transcript: 'nowy',
        selectionStart: 6,
        selectionEnd: 11,
      })
    ).toEqual({ value: 'Dodaj nowy tekst', cursor: 10 })
  })
})
