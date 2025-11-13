import { useState } from 'react'

export function useToast() {
  const [msg, setMsg] = useState<string>('')
  const [type, setType] = useState<'ok'|'err'>('ok')
  const [visible, setVisible] = useState(false)
  function show(message: string, t: 'ok'|'err'='ok', ms=2000) {
    setMsg(message); setType(t); setVisible(true)
    window.setTimeout(()=> setVisible(false), ms)
  }
  const Toast = () => visible ? <div role="status" className={`toast ${type}`}>{msg}</div> : null
  return { show, Toast }
}

