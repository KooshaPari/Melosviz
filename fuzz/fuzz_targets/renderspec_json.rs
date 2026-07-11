#![no_main]

use libfuzzer_sys::fuzz_target;
use melosviz_mir::RenderSpec;

fuzz_target!(|data: &[u8]| {
    // Never panic on hostile JSON — deserialize must be total for fuzzing.
    if let Ok(text) = std::str::from_utf8(data) {
        let _ = serde_json::from_str::<RenderSpec>(text);
    }
});
