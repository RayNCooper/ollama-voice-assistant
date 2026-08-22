//! Ollama Voice Assistant — Tauri 2 desktop shell.
//!
//! Architecture
//! ------------
//! Tauri is only the desktop shell. It does NOT reimplement any of the app;
//! it reuses the exact same pieces the CLI (`ova.sh`) uses:
//!
//!   * the FastAPI backend  — `uvicorn ova.api:app --port 5173`  (ASR + LLM + TTS)
//!   * the static frontend  — `python -m http.server 8000`       (serves index.html)
//!
//! Both are spawned as managed child processes on launch and killed on exit.
//!
//! Why two processes and not just uvicorn?
//! ---------------------------------------
//! The repo-root `index.html` fetches `http://localhost:5173/chat`, and the
//! backend (`ova/api.py`) only whitelists these CORS origins:
//!
//!     http://localhost:5173, http://localhost:8000
//!
//! If we loaded index.html from a Tauri custom scheme (e.g. `tauri://localhost`)
//! the POST to :5173 would be a cross-origin request from a non-whitelisted
//! origin and CORS would block it. Since we must not modify `ova/api.py` or
//! `index.html`, the webview has to load the page from one of the two allowed
//! origins. `ova/api.py` has no `GET /` route, so we serve the static file on
//! :8000 (exactly as `ova.sh` does) and point the webview there. Loopback HTTP
//! is exempt from macOS App Transport Security, so this loads fine in a release
//! build.

use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

const BACKEND_PORT: u16 = 5173;
const FRONTEND_PORT: u16 = 8000;

/// Child processes we own (backend + static frontend). Killed on app exit.
struct Sidecars(Mutex<Vec<Child>>);

/// Locate the repository root (where `ova/`, `index.html`, and `.venv/` live).
///
/// Prefer an explicit `OVA_REPO_DIR` override; otherwise fall back to the
/// compile-time manifest location. `CARGO_MANIFEST_DIR` is `<repo>/tauri/src-tauri`,
/// so the repo root is two levels up. This is baked in at build time, which is
/// fine for a locally built desktop tool: the `.app` runs on the same machine
/// where it was built and the repo (with its `.venv` and model weights) stays
/// in place. Move the `.app` elsewhere and you must set `OVA_REPO_DIR`.
fn repo_root() -> PathBuf {
    if let Ok(dir) = std::env::var("OVA_REPO_DIR") {
        return PathBuf::from(dir);
    }
    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest
        .parent() // <repo>/tauri
        .and_then(Path::parent) // <repo>
        .map(Path::to_path_buf)
        .unwrap_or(manifest)
}

/// Absolute path to a binary inside the repo's uv virtualenv, if it exists.
///
/// Using the venv binary directly (with its absolute-path shebang) means we do
/// not depend on `uv` being on `PATH`, which matters on macOS where apps
/// launched from Finder get a minimal `PATH`.
fn venv_bin(root: &Path, name: &str) -> Option<PathBuf> {
    let p = root.join(".venv").join("bin").join(name);
    p.exists().then_some(p)
}

/// Build a `Command`, forwarding the Ollama Cloud environment to the child.
///
/// `OLLAMA_API_KEY` / `OLLAMA_HOST` are inherited automatically (std inherits
/// the parent environment), but we default `OLLAMA_HOST` if it is unset so the
/// pipeline talks to Ollama Cloud out of the box.
fn base_command(program: PathBuf, root: &Path) -> Command {
    let mut cmd = Command::new(program);
    cmd.current_dir(root);
    if std::env::var_os("OLLAMA_HOST").is_none() {
        cmd.env("OLLAMA_HOST", "https://ollama.com/v1");
    }
    cmd
}

/// Spawn the FastAPI backend: `uvicorn ova.api:app --host 127.0.0.1 --port 5173`.
///
/// No `--reload`: reload spawns a supervisor + worker pair that is harder to
/// reap cleanly; a single process is killed reliably on exit.
fn spawn_backend(root: &Path) -> std::io::Result<Child> {
    let mut cmd = match venv_bin(root, "uvicorn") {
        Some(uvicorn) => base_command(uvicorn, root),
        // Fall back to `uv run` if the venv layout differs; requires uv on PATH.
        None => {
            let mut c = base_command(PathBuf::from("uv"), root);
            c.args(["run", "--no-sync", "uvicorn"]);
            c
        }
    };
    cmd.args([
        "ova.api:app",
        "--host",
        "127.0.0.1",
        "--port",
        &BACKEND_PORT.to_string(),
    ]);
    cmd.spawn()
}

/// Spawn the static frontend server that serves the repo-root `index.html`.
/// `python -m http.server` serves `index.html` for `/` automatically.
fn spawn_frontend(root: &Path) -> std::io::Result<Child> {
    let mut cmd = match venv_bin(root, "python3").or_else(|| venv_bin(root, "python")) {
        Some(python) => base_command(python, root),
        None => {
            let mut c = base_command(PathBuf::from("uv"), root);
            c.args(["run", "--no-sync", "python3"]);
            c
        }
    };
    cmd.args([
        "-m",
        "http.server",
        &FRONTEND_PORT.to_string(),
        "--bind",
        "127.0.0.1",
    ]);
    cmd.spawn()
}

/// Block until `127.0.0.1:port` accepts a TCP connection, or `timeout` elapses.
fn wait_for_port(port: u16, timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(150));
    }
    false
}

/// Kill every child process we spawned. Idempotent (drains the vec).
fn kill_sidecars(app: &tauri::AppHandle) {
    if let Some(state) = app.try_state::<Sidecars>() {
        if let Ok(mut children) = state.0.lock() {
            for mut child in children.drain(..) {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

pub fn run() {
    tauri::Builder::default()
        .manage(Sidecars(Mutex::new(Vec::new())))
        .setup(|app| {
            let root = repo_root();
            eprintln!("[ova] repo root: {}", root.display());

            let mut children = Vec::new();
            match spawn_backend(&root) {
                Ok(child) => {
                    eprintln!("[ova] backend (uvicorn) started on :{BACKEND_PORT}");
                    children.push(child);
                }
                Err(e) => eprintln!("[ova] failed to start backend: {e}"),
            }
            match spawn_frontend(&root) {
                Ok(child) => {
                    eprintln!("[ova] frontend (http.server) started on :{FRONTEND_PORT}");
                    children.push(child);
                }
                Err(e) => eprintln!("[ova] failed to start frontend: {e}"),
            }
            *app.state::<Sidecars>().0.lock().unwrap() = children;

            // Wait for the static server so the window loads the real UI rather
            // than a connection error. The backend can keep warming up (model
            // load) in the background; index.html handles a slow first request.
            if !wait_for_port(FRONTEND_PORT, Duration::from_secs(15)) {
                eprintln!("[ova] frontend did not open :{FRONTEND_PORT} in time; loading anyway");
            }

            WebviewWindowBuilder::new(
                app,
                "main",
                WebviewUrl::External(
                    format!("http://localhost:{FRONTEND_PORT}").parse().unwrap(),
                ),
            )
            .title("Ollama Voice Assistant by Olio Solutions")
            .inner_size(900.0, 700.0)
            .min_inner_size(600.0, 500.0)
            .build()?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the Ollama Voice Assistant")
        .run(|app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                kill_sidecars(app_handle);
            }
        });
}
