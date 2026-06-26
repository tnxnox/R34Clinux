// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    #[cfg(target_os = "linux")]
    {
        // Fix for WebKitGTK / GDK protocol errors on Wayland (e.g. Error 71)
        if std::env::var("WEBKIT_DISABLE_DMABUF_RENDERER").is_err() {
            unsafe {
                std::env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "1");
            }
        }
        // Fix for GStreamer stuttering/buffering issues on WebKitGTK
        if std::env::var("WEBKIT_GST_DMABUF_SINK_DISABLED").is_err() {
            unsafe {
                std::env::set_var("WEBKIT_GST_DMABUF_SINK_DISABLED", "1");
            }
        }
    }
    r34client_lib::run()
}
