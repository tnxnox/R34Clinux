use std::path::Path;
use std::process::Command;

fn has_command(cmd: &str) -> bool {
    Command::new(cmd)
        .arg("--version")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .is_ok()
}

fn check_prerequisites() -> bool {
    if !has_command("node") || !has_command("npm") {
        return false;
    }

    #[cfg(target_os = "linux")]
    {
        let has_pkgconfig = Command::new("pkg-config")
            .arg("--version")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false);

        if !has_pkgconfig {
            return false;
        }

        let has_webkit = Command::new("pkg-config")
            .arg("--exists")
            .arg("webkit2gtk-4.1")
            .status()
            .map(|s| s.success())
            .unwrap_or(false);

        if !has_webkit {
            return false;
        }
    }

    true
}

fn main() {
    println!("cargo:rerun-if-changed=tauri.conf.json");
    println!("cargo:rerun-if-changed=capabilities");

    // 1. Check prerequisites and warn if missing (avoid interactive sudo in build script)
    if !check_prerequisites() {
        println!(
            "cargo:warning=Missing prerequisites (Node.js, npm, or WebKit2GTK). If the build fails, run: bash scripts/setup.sh"
        );
    }

    // 2. Build frontend assets only if dist is missing or empty
    // Note: `npm run tauri build` already runs `beforeBuildCommand: "npm run build"`
    let dist_dir = Path::new("..").join("dist");
    let dist_empty = !dist_dir.exists()
        || dist_dir
            .read_dir()
            .map(|mut d| d.next().is_none())
            .unwrap_or(true);

    if dist_empty && has_command("npm") {
        println!("cargo:warning=Frontend dist is missing or empty; building frontend assets...");

        let npm_build = Command::new("npm")
            .args(["run", "build"])
            .current_dir("..")
            .status();

        if let Err(e) = npm_build {
            println!(
                "cargo:warning=Failed to invoke npm run build: {}. Frontend assets might be missing.",
                e
            );
        } else if let Ok(status) = npm_build
            && !status.success()
        {
            println!(
                "cargo:warning=npm run build exited with non-zero status: {}.",
                status
            );
        }
    }

    tauri_build::build()
}
