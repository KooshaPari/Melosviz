#![no_main]

use libfuzzer_sys::fuzz_target;
// The previous implementation referenced `melosviz_mir::wav::load_wav_mono`,
// which no longer exists in the crate. `melosviz_mir::read_wav_header` is
// the closest public analogue and is exercised against hostile bytes here
// to keep the fuzz harness meaningful.
use melosviz_mir::read_wav_header;
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
    // read_wav_header returns Result for invalid WAV bytes; the point of
    // fuzzing is to make sure it never panics on hostile input.
    let _ = read_wav_header(tmp.path());
});
