import { invoke } from '@tauri-apps/api/tauri'

type Settings = {
  server_url: string
  whisper_exe: string
  whisper_model: string
  whisper_model_preset: string
  vad: boolean
  vad_threshold: number
  max_seconds: number
  tts_cmd: string
  tts_voice: string
  tts_rate: number
}

async function loadSettings() {
  const s = await invoke<Settings>('get_settings')
  ;(document.getElementById('server') as HTMLInputElement).value = s.server_url
  ;(document.getElementById('whisperExe') as HTMLInputElement).value = s.whisper_exe
  ;(document.getElementById('whisperModel') as HTMLInputElement).value = s.whisper_model
  ;(document.getElementById('modelPreset') as HTMLSelectElement).value = s.whisper_model_preset || 'large-v3'
  ;(document.getElementById('vad') as HTMLInputElement).checked = s.vad
  ;(document.getElementById('maxSec') as HTMLInputElement).value = String(s.max_seconds)
  ;(document.getElementById('voice') as HTMLInputElement).value = s.tts_voice
}

async function saveSettings() {
  const s: Settings = {
    server_url: (document.getElementById('server') as HTMLInputElement).value,
    whisper_exe: (document.getElementById('whisperExe') as HTMLInputElement).value,
    whisper_model: (document.getElementById('whisperModel') as HTMLInputElement).value,
    whisper_model_preset: (document.getElementById('modelPreset') as HTMLSelectElement).value,
    vad: (document.getElementById('vad') as HTMLInputElement).checked,
    vad_threshold: 0.5,
    max_seconds: parseInt((document.getElementById('maxSec') as HTMLInputElement).value||'90'),
    tts_cmd: 'tts',
    tts_voice: (document.getElementById('voice') as HTMLInputElement).value,
    tts_rate: 1.0,
  }
  await invoke('save_settings', { cfg: s })
  ;(document.getElementById('saved')!).textContent = 'OK'
  setTimeout(()=>{ (document.getElementById('saved')!).textContent = '' }, 1000)
}

async function transcribe() {
  const f = (document.getElementById('wav') as HTMLInputElement).files?.[0]
  if (!f) return
  // tauri cannot access File path directly; assume user selects a path via file input (fs scope). For demo, save to temp.
  const buf = await f.arrayBuffer()
  const tmp = await (window as any).__TAURI__.path.appCacheDir()
  const fp = tmp + '/input.wav'
  await (window as any).__TAURI__.fs.writeBinaryFile({ path: fp, contents: new Uint8Array(buf) })
  const text = await invoke<string>('transcribe_wav', { wavPath: fp })
  ;(document.getElementById('text') as HTMLTextAreaElement).value = text
}

async function speak() {
  const text = (document.getElementById('text') as HTMLTextAreaElement).value
  if (!text.trim()) return
  await invoke('tts_speak', { text })
}

async function sendToServer() {
  const text = (document.getElementById('text') as HTMLTextAreaElement).value
  const server = (document.getElementById('server') as HTMLInputElement).value.replace(/\/$/, '')
  const res = await fetch(server + '/llm/infer', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ prompt: text }) })
  const data = await res.json()
  ;(document.getElementById('resp')!).textContent = data.text || JSON.stringify(data)
}

async function checkUpdate() {
  const mani = await invoke<any>('check_update')
  const el = document.getElementById('upd')!
  if (!mani) { el.textContent = 'Aucune mise à jour détectée'; return }
  el.textContent = `Version ${mani.version} disponible`
}

document.getElementById('save')!.addEventListener('click', saveSettings)
document.getElementById('stt')!.addEventListener('click', transcribe)
document.getElementById('speak')!.addEventListener('click', speak)
document.getElementById('send')!.addEventListener('click', sendToServer)
document.getElementById('checkUpdate')!.addEventListener('click', checkUpdate)

function recommendedPath(preset: string) {
  // Chemins Windows recommandés
  if (preset === 'small') return 'C:/IVY/models/whisper/ggml-small.bin'
  return 'C:/IVY/models/whisper/ggml-large-v3.bin'
}

function applyPreset() {
  const preset = (document.getElementById('modelPreset') as HTMLSelectElement).value
  ;(document.getElementById('whisperModel') as HTMLInputElement).value = recommendedPath(preset)
}

document.getElementById('applyPreset')!.addEventListener('click', applyPreset)

loadSettings()
