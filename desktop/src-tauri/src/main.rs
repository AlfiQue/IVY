#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DesktopSettings {
    pub server_url: String,
    pub whisper_exe: String,
    pub whisper_model: String,
    pub whisper_model_preset: String,
    pub vad: bool,
    pub vad_threshold: f32,
    pub max_seconds: u32,
    pub tts_cmd: String,
    pub tts_voice: String,
    pub tts_rate: f32,
}

impl Default for DesktopSettings {
    fn default() -> Self {
        Self {
            server_url: "http://127.0.0.1:8000".into(),
            whisper_exe: "C:/tools/whisper/whisper.exe".into(),
            whisper_model: "C:/tools/whisper/ggml-large-v3.bin".into(),
            whisper_model_preset: "large-v3".into(),
            vad: true,
            vad_threshold: 0.5,
            max_seconds: 90,
            tts_cmd: "tts".into(),
            tts_voice: "tts_models/fr/css10/vits".into(),
            tts_rate: 1.0,
        }
    }
}

fn settings_path() -> PathBuf {
    let dir = dirs::config_dir()
        .unwrap_or(std::env::temp_dir())
        .join("ivy-desktop");
    let _ = fs::create_dir_all(&dir);
    dir.join("settings.json")
}

#[tauri::command]
fn get_settings() -> Result<DesktopSettings, String> {
    let p = settings_path();
    if p.exists() {
        let s = fs::read_to_string(&p).map_err(|e| e.to_string())?;
        let cfg: DesktopSettings = serde_json::from_str(&s).map_err(|e| e.to_string())?;
        Ok(cfg)
    } else {
        Ok(DesktopSettings::default())
    }
}

#[tauri::command]
fn save_settings(cfg: DesktopSettings) -> Result<(), String> {
    let p = settings_path();
    let s = serde_json::to_string_pretty(&cfg).map_err(|e| e.to_string())?;
    fs::write(p, s).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
fn transcribe_wav(wav_path: String) -> Result<String, String> {
    let cfg = get_settings()?;
    let mut args: Vec<String> = vec![
        "--model".into(),
        cfg.whisper_model,
        "-f".into(),
        wav_path.clone(),
        "-l".into(),
        "fr".into(),
        "--output-txt".into(),
        "--no-timestamps".into(),
    ];
    if cfg.vad {
        args.push("--vad".into());
    }
    // si whisper.cpp supporte --duration
    args.push("--duration".into());
    args.push(cfg.max_seconds.to_string());

    let out_dir = std::env::temp_dir().join("ivy_whisper");
    let _ = fs::create_dir_all(&out_dir);
    args.push("--output-dir".into());
    args.push(out_dir.to_string_lossy().to_string());

    let status = Command::new(cfg.whisper_exe)
        .args(&args)
        .status()
        .map_err(|e| format!("whisper exec: {}", e))?;
    if !status.success() {
        return Err("whisper failed".into());
    }
    // lire le .txt généré
    let stem = Path::new(&wav_path)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("out")
        .to_string();
    let txt_path = out_dir.join(format!("{}.txt", stem));
    let txt = fs::read_to_string(&txt_path).map_err(|e| e.to_string())?;
    Ok(txt)
}

#[tauri::command]
fn tts_speak(text: String) -> Result<(), String> {
    let cfg = get_settings()?;
    // Génère un WAV temporaire via Coqui TTS
    let out = std::env::temp_dir().join("ivy_tts.wav");
    let mut args: Vec<String> = vec![
        "--text".into(),
        text,
        "--model_name".into(),
        cfg.tts_voice,
        "--out_path".into(),
        out.to_string_lossy().to_string(),
    ];
    // Pas de flag standard pour le rate: dépend du modèle; laissé à 1.0
    let status = Command::new(&cfg.tts_cmd)
        .args(&args)
        .status()
        .map_err(|e| format!("tts exec: {}", e))?;
    if !status.success() {
        return Err("tts failed".into());
    }
    // Lire via lecteur par défaut
    let _ = Command::new("C:/Windows/System32/cmd.exe")
        .args(["/C", &format!("start \"\" {}", out.to_string_lossy())])
        .status();
    Ok(())
}

#[derive(Debug, Serialize, Deserialize)]
struct UpdateManifest {
    version: String,
    url: String,
    sha256: String,
    notes: Option<String>,
}

#[tauri::command]
fn check_update() -> Result<Option<UpdateManifest>, String> {
    let cfg = get_settings()?;
    let url = format!("{}/updates/desktop/manifest.json", cfg.server_url.trim_end_matches('/'));
    let resp = reqwest::blocking::get(&url).map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Ok(None);
    }
    let mani: UpdateManifest = resp.json().map_err(|e| e.to_string())?;
    Ok(Some(mani))
}

#[tauri::command]
fn download_and_verify(url: String, sha256_hex: String) -> Result<String, String> {
    let bytes = reqwest::blocking::get(&url)
        .map_err(|e| e.to_string())?
        .bytes()
        .map_err(|e| e.to_string())?;
    let mut hasher = Sha256::new();
    hasher.update(&bytes);
    let digest = hasher.finalize();
    let calc = hex::encode(digest);
    if calc.to_lowercase() != sha256_hex.to_lowercase() {
        return Err("SHA256 mismatch".into());
    }
    let path = std::env::temp_dir().join("ivy_desktop_update.msi");
    fs::write(&path, &bytes).map_err(|e| e.to_string())?;
    Ok(path.to_string_lossy().to_string())
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            get_settings,
            save_settings,
            transcribe_wav,
            tts_speak,
            check_update,
            download_and_verify
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
