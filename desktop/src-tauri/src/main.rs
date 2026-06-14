use melosviz_desktop::menu::build_menu;
use tauri::tray::TrayIconBuilder;

fn main() {
    tauri::Builder::default()
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

#[cfg(test)]
mod tests {
    use ctrlc;

    #[test]
    fn test_ctrlc_set_handler() {
        ctrlc::set_handler(|| println!("Received Ctrl+C")).unwrap();
    }
}
