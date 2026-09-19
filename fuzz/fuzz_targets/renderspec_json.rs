#![no_main]

use libfuzzer_sys::fuzz_target;
// RenderSpec lives in the Rust SDK (sdk/rust/src/types.rs); the melosviz-mir
// crate mirrors its JSON shape but does not itself define the struct.
use melosviz_sdk::RenderSpec;

fuzz_target!(|data: &[u8]| {
    // Never panic on hostile JSON — deserialize must be total for fuzzing.
    if let Ok(text) = std::str::from_utf8(data) {
        let _ = serde_json::from_str::<RenderSpec>(text);
    }
});
