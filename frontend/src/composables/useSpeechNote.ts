import { computed, ref, type Ref } from 'vue'

interface SpeechResultEvent {
  results: ArrayLike<{ 0: { transcript: string } }>
}

interface SpeechRecognizer {
  lang: string
  interimResults: boolean
  start: () => void
  stop: () => void
  onresult: ((event: SpeechResultEvent) => void) | null
  onerror: (() => void) | null
  onend: (() => void) | null
}

type SpeechRecognizerConstructor = new () => SpeechRecognizer
type SpeechWindow = Window & {
  SpeechRecognition?: SpeechRecognizerConstructor
  webkitSpeechRecognition?: SpeechRecognizerConstructor
}

export function useSpeechNote(target: Ref<string>) {
  const Recognizer = (window as SpeechWindow).SpeechRecognition
    || (window as SpeechWindow).webkitSpeechRecognition
  const listening = ref(false)
  const message = ref('')
  let recognition: SpeechRecognizer | null = null

  function toggle() {
    if (!Recognizer) return
    if (recognition && listening.value) {
      recognition.stop()
      return
    }
    recognition = new Recognizer()
    recognition.lang = 'zh-CN'
    recognition.interimResults = false
    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript?.trim()
      if (transcript) target.value = [target.value.trim(), transcript].filter(Boolean).join(' ')
    }
    recognition.onerror = () => { message.value = '这次没有听清，也可以直接打字。' }
    recognition.onend = () => { listening.value = false }
    message.value = ''
    listening.value = true
    try { recognition.start() }
    catch {
      listening.value = false
      message.value = '这次没有听清，也可以直接打字。'
    }
  }

  return { supported: computed(() => Boolean(Recognizer)), listening, message, toggle }
}
