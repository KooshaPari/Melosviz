//! Melosviz Desktop entrypoint.
//!
//! Builds a Tauri app with IPC handlers that bridge the frontend to the
//! Python FastAPI backend on localhost:8000.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use melosviz_desktop_lib::menu::build_menu;
use melosviz_desktop_lib::PlaybackState;
use std::sync::Mutex;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(Mutex::new(PlaybackState::default()))
        .invoke_handler(tauri::generate_handler![
            melosviz_desktop_lib::health_check,
            melosviz_desktop_lib::get_presets,
            melosviz_desktop_lib::playback_control,
            melosviz_desktop_lib::upload_audio,
            melosviz_desktop_lib::render_visualization,
        ])
        .setup(|app| {
            let menu = build_menu(app.handle());
            app.set_menu(menu).expect("error setting menu");
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Tauri application");
}

#[cfg(test)]
mod tests {
    use ctrlc;

    #[test]
    fn test_ctrlc_set_handler() {
        ctrlc::set_handler(|| println!("Received Ctrl+C")).unwrap();
    }
}
