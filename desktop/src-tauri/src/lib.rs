use std::net::TcpListener;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{Manager, State};
use std::path::PathBuf;

struct ApiState {
    port: u16,
    child: Mutex<Option<Child>>,
}

#[tauri::command]
fn get_api_port(state: State<'_, ApiState>) -> u16 {
    state.port
}

fn get_free_port() -> Option<u16> {
    TcpListener::bind("127.0.0.1:0")
        .ok()
        .and_then(|listener| listener.local_addr().ok())
        .map(|addr| addr.port())
}

fn spawn_sidecar(port: u16) -> Option<Child> {
    let port_str = port.to_string();
    
    if cfg!(debug_assertions) {
        // Development mode: run Python module
        let paths_to_check = [
            PathBuf::from("../.venv/bin/python"),
            PathBuf::from("./.venv/bin/python"),
            PathBuf::from("python3"),
        ];

        for python_path in paths_to_check {
            let mut cmd = Command::new(&python_path);
            cmd.args(&["-m", "r34_client", "--port", &port_str]);
            
            // If python is in the parent .venv, set cwd to parent directory
            if python_path.to_string_lossy().starts_with("../") {
                cmd.current_dir("..");
            }
            
            cmd.stdout(Stdio::inherit());
            cmd.stderr(Stdio::inherit());

            if let Ok(child) = cmd.spawn() {
                println!("Spawned Python sidecar dev server using {:?} on port {}", python_path, port);
                return Some(child);
            }
        }
        None
    } else {
        // Production mode: run compiled sidecar binary
        if let Ok(exe_path) = std::env::current_exe() {
            if let Some(exe_dir) = exe_path.parent() {
                let sidecar_path = exe_dir.join("r34-client-sidecar");
                if sidecar_path.exists() {
                    let mut cmd = Command::new(&sidecar_path);
                    cmd.args(&["--port", &port_str]);
                    if let Ok(child) = cmd.spawn() {
                        return Some(child);
                    }
                }
            }
        }
        None
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let port = get_free_port().unwrap_or(8000);
            let child = spawn_sidecar(port);
            app.manage(ApiState {
                port,
                child: Mutex::new(child),
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state = window.state::<ApiState>();
                let guard = state.child.lock();
                if let Ok(mut child_guard) = guard {
                    if let Some(mut child) = child_guard.take() {
                        let _ = child.kill();
                        println!("Killed Python sidecar process.");
                    }
                }
            }
        })
        .invoke_handler(tauri::generate_handler![get_api_port])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
