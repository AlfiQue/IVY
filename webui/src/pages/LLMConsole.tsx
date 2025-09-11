import { useRef, useState } from 'react'
import { api, connectLLMStream } from '../api/client'

export default function LLMConsole() {
  const [prompt, setPrompt] = useState('Bonjour !')
  const [result, setResult] = useState('')
  const [streaming, setStreaming] = useState(false)
  const wsRef = useRef<ReturnType<typeof connectLLMStream> | null>(null)

  async function infer() {
    const data = await api.infer(prompt)
    setResult(data.text)
  }
  function startStream() {
    setResult('')
    const c = connectLLMStream(prompt)
    wsRef.current = c
    setStreaming(true)
    c.start(
      (t)=> setResult(prev => prev + t),
      ()=> { setStreaming(false); wsRef.current = null },
      (_)=> { setStreaming(false); wsRef.current = null }
    )
  }
  function stopStream() { wsRef.current?.close(); setStreaming(false) }

  return (
    <section>
      <h2>LLM</h2>
      <textarea value={prompt} onChange={e=>setPrompt(e.target.value)} rows={5} style={{width:'100%'}} aria-label="Invite" />
      <div className="row">
        <button onClick={infer}>Exécuter (non stream)</button>
        {!streaming ? <button onClick={startStream}>Streamer</button> : <button onClick={stopStream}>Arrêter</button>}
      </div>
      <pre aria-live="polite" style={{whiteSpace:'pre-wrap'}}>{result}</pre>
    </section>
  )
}

