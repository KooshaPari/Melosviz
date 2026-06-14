//! Native menu bar for Melosviz Desktop.
//!
//! Provides standard macOS menus: File, Edit, View, Help with keyboard shortcuts.

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem, Submenu};
use tauri::Runtime;

/// Build the application menu bar.
pub fn build_menu<R: Runtime>(app: &tauri::AppHandle<R>) -> tauri::Result<Menu<R>> {
    let menu = Menu::new(app)?;

    // File menu
    let file_menu = Submenu::new(app, "File", true)?;
    let open = MenuItem::new(app, "Open", true, Some("CmdOrCtrl+O"))?;
    let save = MenuItem::new(app, "Save", true, Some("CmdOrCtrl+S"))?;
    let export = MenuItem::new(app, "Export...", true, Some("CmdOrCtrl+Shift+E"))?;
    let sep1 = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::new(app, "Quit", true, Some("CmdOrCtrl+Q"))?;
    file_menu.append_items(&[&open, &save, &export, &sep1, &quit])?;

    // Edit menu
    let edit_menu = Submenu::new(app, "Edit", true)?;
    let undo = MenuItem::new(app, "Undo", true, Some("CmdOrCtrl+Z"))?;
    let redo = MenuItem::new(app, "Redo", true, Some("CmdOrCtrl+Shift+Z"))?;
    let sep2 = PredefinedMenuItem::separator(app)?;
    let cut = MenuItem::new(app, "Cut", true, Some("CmdOrCtrl+X"))?;
    let copy = MenuItem::new(app, "Copy", true, Some("CmdOrCtrl+C"))?;
    let paste = MenuItem::new(app, "Paste", true, Some("CmdOrCtrl+V"))?;
    let sep3 = PredefinedMenuItem::separator(app)?;
    let select_all = MenuItem::new(app, "Select All", true, Some("CmdOrCtrl+A"))?;
    edit_menu.append_items(&[&undo, &redo, &sep2, &cut, &copy, &paste, &sep3, &select_all])?;

    // View menu
    let view_menu = Submenu::new(app, "View", true)?;
    let reload = MenuItem::new(app, "Reload", true, Some("CmdOrCtrl+R"))?;
    let toggle_fullscreen = MenuItem::new(app, "Toggle Full Screen", true, Some("CmdOrCtrl+Shift+F"))?;
    let sep4 = PredefinedMenuItem::separator(app)?;
    let zoom_in = MenuItem::new(app, "Zoom In", true, Some("CmdOrCtrl+Plus"))?;
    let zoom_out = MenuItem::new(app, "Zoom Out", true, Some("CmdOrCtrl+Minus"))?;
    view_menu.append_items(&[&reload, &toggle_fullscreen, &sep4, &zoom_in, &zoom_out])?;

    // Help menu
    let help_menu = Submenu::new(app, "Help", true)?;
    let docs = MenuItem::new(app, "Documentation", true, None::<&str>)?;
    let sep5 = PredefinedMenuItem::separator(app)?;
    let about = MenuItem::new(app, "About Melosviz", true, None::<&str>)?;
    help_menu.append_items(&[&docs, &sep5, &about])?;

    menu.append_items(&[&file_menu, &edit_menu, &view_menu, &help_menu])?;

    Ok(menu)
}
