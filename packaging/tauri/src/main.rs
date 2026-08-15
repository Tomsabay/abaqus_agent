// Prevent an extra console window on Windows in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::Write;
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use tauri::Manager;

/// Holds the spawned backend process so it can be killed on exit.
struct Backend(Mutex<Option<Child>>);

const DEFAULT_PORT: u16 = 8760;

/// Append a diagnostic line to shell.log in the data dir. stdout is block-
/// buffered when the GUI process has no console, so file logging is what we
/// can actually read while the app runs.
fn log_line(data_dir: &std::path::Path, msg: &str) {
    let _ = std::fs::create_dir_all(data_dir);
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(data_dir.join("shell.log"))
    {
        let _ = writeln!(f, "{msg}");
    }
}

/// Resolve the backend server executable.
///
/// 1. ABAQUS_AGENT_BACKEND_EXE env (explicit; used during `tauri dev`)
/// 2. bundled resource (packaged app, stage 3)
/// 3. dev fallback: repo dist/ built by PyInstaller
fn resolve_backend_exe(app: &tauri::AppHandle) -> Option<PathBuf> {
    if let Ok(p) = std::env::var("ABAQUS_AGENT_BACKEND_EXE") {
        let path = PathBuf::from(p);
        if path.is_file() {
            return Some(path);
        }
    }
    // Bundled resource. Tauri's resource-dir layout for a mapped folder varies,
    // so check both likely paths, then fall back to a shallow recursive search.
    if let Ok(res_dir) = app.path().resource_dir() {
        let candidates = [
            res_dir.join("backend").join("abaqus-agent-server.exe"),
            res_dir
                .join("backend")
                .join("abaqus-agent-server")
                .join("abaqus-agent-server.exe"),
        ];
        for c in candidates {
            if c.is_file() {
                return Some(c);
            }
        }
        if let Some(found) = find_backend_exe(&res_dir, 4) {
            return Some(found);
        }
    }
    // Dev fallback: packaging/tauri/ -> repo root -> dist/...
    let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("dist")
        .join("abaqus-agent-server")
        .join("abaqus-agent-server.exe");
    if dev.is_file() {
        return Some(dev);
    }
    None
}

/// Shallow recursive search for abaqus-agent-server.exe (bundled-layout guard).
fn find_backend_exe(dir: &std::path::Path, depth: u8) -> Option<PathBuf> {
    if depth == 0 {
        return None;
    }
    let entries = std::fs::read_dir(dir).ok()?;
    let mut subdirs = Vec::new();
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_file() && path.file_name()? == "abaqus-agent-server.exe" {
            return Some(path);
        }
        if path.is_dir() {
            subdirs.push(path);
        }
    }
    for sub in subdirs {
        if let Some(found) = find_backend_exe(&sub, depth - 1) {
            return Some(found);
        }
    }
    None
}

fn port() -> u16 {
    std::env::var("ABAQUS_AGENT_PORT")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(DEFAULT_PORT)
}

/// Spawn the backend, storing the child for cleanup. Returns false on failure.
fn spawn_backend(app: &tauri::AppHandle) -> bool {
    let data_dir = app
        .path()
        .app_data_dir()
        .unwrap_or_else(|_| PathBuf::from("."));
    let _ = std::fs::create_dir_all(&data_dir);

    let exe = match resolve_backend_exe(app) {
        Some(e) => e,
        None => {
            log_line(&data_dir, "[shell] backend exe not found (resolve returned None)");
            return false;
        }
    };
    // Canonicalize away any ../ segments from the dev-fallback path so both the
    // program path and cwd are clean absolute paths for CreateProcess.
    let exe = std::fs::canonicalize(&exe).unwrap_or(exe);
    log_line(&data_dir, &format!("[shell] resolved exe: {}", exe.display()));

    // Send the backend's own stdout/stderr to a file we can inspect.
    let out = std::fs::File::create(data_dir.join("backend.log")).ok();
    let err = std::fs::File::create(data_dir.join("backend.err.log")).ok();

    let mut cmd = Command::new(&exe);
    cmd.env("ABAQUS_AGENT_PORT", port().to_string())
        .env("ABAQUS_AGENT_DATA_DIR", data_dir.as_os_str())
        .env("ABAQUS_AGENT_DEV", "0");
    if let Some(dir) = exe.parent() {
        cmd.current_dir(dir);
    }
    if let Some(f) = out {
        cmd.stdout(Stdio::from(f));
    }
    if let Some(f) = err {
        cmd.stderr(Stdio::from(f));
    }

    match cmd.spawn() {
        Ok(child) => {
            log_line(&data_dir, &format!("[shell] backend spawned pid={}", child.id()));
            let state = app.state::<Backend>();
            *state.0.lock().unwrap() = Some(child);
            true
        }
        Err(e) => {
            log_line(&data_dir, &format!("[shell] spawn failed: {e}"));
            false
        }
    }
}

/// Poll the backend port; once it accepts connections, navigate the window.
fn wait_and_navigate(app: tauri::AppHandle) {
    std::thread::spawn(move || {
        let addr = format!("127.0.0.1:{}", port());
        let deadline = std::time::Instant::now() + Duration::from_secs(90);
        loop {
            if TcpStream::connect_timeout(
                &addr.parse().unwrap(),
                Duration::from_millis(500),
            )
            .is_ok()
            {
                // Give uvicorn a beat to finish app startup after bind.
                std::thread::sleep(Duration::from_millis(800));
                if let Some(win) = app.get_webview_window("main") {
                    let url = format!("http://127.0.0.1:{}/workbench", port());
                    if let Ok(u) = url.parse() {
                        let _ = win.navigate(u);
                    }
                }
                break;
            }
            if std::time::Instant::now() > deadline {
                eprintln!("[shell] backend did not become ready in time");
                break;
            }
            std::thread::sleep(Duration::from_millis(400));
        }
    });
}

fn kill_backend(app: &tauri::AppHandle) {
    let state = app.state::<Backend>();
    // Take the child out and release the mutex guard on this line, so the
    // guard's borrow does not outlive `state` at the end of the function.
    let taken = state.0.lock().unwrap().take();
    if let Some(mut child) = taken {
        let pid = child.id();
        // Kill the whole tree on Windows (bootloader may hold children).
        #[cfg(target_os = "windows")]
        {
            let _ = Command::new("taskkill")
                .args(["/F", "/T", "/PID", &pid.to_string()])
                .output();
        }
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn main() {
    tauri::Builder::default()
        .manage(Backend(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            if spawn_backend(&handle) {
                wait_and_navigate(handle);
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                kill_backend(window.app_handle());
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
