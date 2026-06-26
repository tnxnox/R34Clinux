use std::env;
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
    // 1. Verify prerequisites and auto-run setup.sh if missing
    if !check_prerequisites() {
        println!("cargo:warning=Missing prerequisites. Running scripts/setup.sh...");
        let setup_status = Command::new("bash").arg("../../scripts/setup.sh").status();

        match setup_status {
            Ok(status) if status.success() => {
                println!("cargo:warning=System dependencies setup completed successfully.");
            }
            _ => {
                panic!("Failed to configure system dependencies using scripts/setup.sh");
            }
        }
    }

    // 2. Build frontend assets if in release mode or if dist is missing/empty
    let profile = env::var("PROFILE").unwrap_or_default();
    let dist_dir = Path::new("..").join("dist");

    if profile == "release"
        || !dist_dir.exists()
        || dist_dir
            .read_dir()
            .map(|mut d| d.next().is_none())
            .unwrap_or(true)
    {
        println!("cargo:warning=Building frontend assets...");

        let npm_install = Command::new("npm")
            .args(["install"])
            .current_dir("..")
            .status();

        match npm_install {
            Ok(status) if status.success() => {
                let npm_build = Command::new("npm")
                    .args(["run", "build"])
                    .current_dir("..")
                    .status();

                if let Err(e) = npm_build {
                    panic!("Failed to run npm run build: {}", e);
                } else if let Ok(status) = npm_build
                    && !status.success()
                {
                    panic!("npm run build failed");
                }
            }
            Ok(status) => {
                panic!("npm install failed with status: {}", status);
            }
            Err(e) => {
                panic!(
                    "Failed to run npm install: {}. Is Node.js/npm installed?",
                    e
                );
            }
        }
    }

    tauri_build::build()
}
