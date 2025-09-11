import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'

export default function VoiceCommand() {
  const [supported, setSupported] = useState(false)
  const [listening, setListening] = useState(false)
  const [text, setText] = useState('')
  const recRef = useRef<any>(null)

  useEffect(()=>{
    const SR = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition
    if (SR) {
      setSupported(true)
      const rec = new SR()
      rec.lang = 'fr-FR'
      rec.interimResults = true
      rec.onresult = (e: any) => {
        let t = ''
        for (const res of e.results) t += res[0].transcript
        setText(t)
      }
      rec.onend = ()=> setListening(false)
      recRef.current = rec
    }
  },[])

  function start() { try { recRef.current?.start(); setListening(true) } catch {}
  }
  function stop() { try { recRef.current?.stop(); setListening(false) } catch {}
  }
  async function send() {
    if (!text.trim()) return
    const res = await api.infer(text)
    alert(res.text)
  }
  return (
    <section>
      <h2>Commande vocale</h2>
      {!supported ? <p className="muted">Reconnaissance vocale non supportée.</p> : (
        <div className="row">
          {!listening ? <button onClick={start} aria-label="Démarrer l'écoute">Démarrer</button> : <button onClick={stop} aria-label="Arrêter l'écoute">Arrêter</button>}
          <button onClick={send} disabled={!text}>Envoyer</button>
        </div>
      )}
      <p>{text}</p>
    </section>
  )
}

