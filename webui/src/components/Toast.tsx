import { useState } from 'react'

type ToastTone = 'ok' | 'err'
type ToastToneInput = ToastTone | 'success' | 'error'

type ToastConfig = {
  message: string
  type?: ToastToneInput
  duration?: number
}

function normalizeTone(input?: ToastToneInput): ToastTone {
  if (input === 'error') return 'err'
  if (input === 'success') return 'ok'
  return input ?? 'ok'
}

export function useToast() {
  const [msg, setMsg] = useState<string>('')
  const [tone, setTone] = useState<ToastTone>('ok')
  const [visible, setVisible] = useState(false)

  function show(arg: string | ToastConfig, t?: ToastToneInput, ms = 2000) {
    const payload: ToastConfig = typeof arg === 'string' ? { message: arg, type: t, duration: ms } : arg
    const duration = payload.duration ?? ms
    setMsg(payload.message)
    setTone(normalizeTone(payload.type))
    setVisible(true)
    window.setTimeout(() => setVisible(false), duration)
  }

  const Toast = () =>
    visible ? (
      <div role="status" className={`toast ${tone}`}>
        {msg}
      </div>
    ) : null

  return { show, Toast }
}
