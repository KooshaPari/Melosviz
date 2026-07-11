#![no_main]

use libfuzzer_sys::fuzz_target;
use melosviz_mir::wav::load_wav_mono;
use std::io::Write;

fuzz_target!(|data: &[u8]| {
    // Cap input so CI/nightly stays bounded.
    let bytes = if data.len() > 64 * 1024 {
        &data[..64 * 1024]
    } else {
        data
    };
    let Ok(mut tmp) = tempfile::Builder::new().suffix(".wav").tempfile() else {
        return;
    };
    if tmp.write_all(bytes).is_err() {
        return;
    }
    let _ = tmp.flush();
    let _ = load_wav_mono(tmp.path());
});
