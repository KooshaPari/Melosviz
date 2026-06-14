use melosviz_desktop::commands::PlaybackState;
use melosviz_desktop::menu::build_menu;
use tauri::tray::TrayIconBuilder;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(std::sync::Mutex::new(PlaybackState::default()))
        .invoke_handler(tauri::generate_handler![
            melosviz_desktop::commands::upload_audio,
            melosviz_desktop::commands::render_visualization,
            melosviz_desktop::commands::playback_control,
            melosviz_desktop::commands::get_presets,
            melosviz_desktop::commands::health_check,
            melosviz_desktop::dialog::open_midi_file,
            melosviz_desktop::dialog::save_mp4_file,
            melosviz_desktop::notify::send_notification,
            melosviz_desktop::deeplink::parse_deep_link,
            melosviz_desktop::updater::check_update,
            melosviz_desktop::updater::apply_update,
        ])
        .setup(|app| {
            #[cfg(target_os = "macos")]
            {
                let menu = build_menu(app.handle())?;
                app.set_menu(menu.clone())?;

                TrayIconBuilder::new()
                    .icon(app.default_window_icon().unwrap().clone())
                    .tooltip("Melosviz Desktop")
                    .menu(&menu)
                    .show_menu_on_left_click(true)
                    .build(app)?;
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
