//! Melosviz MIR (Music Intermediate Representation) — stub crate.
//!
//! This is a no-op placeholder so that workspace-level CI checks
//! (`cargo metadata --locked`, `cargo bench -p melosviz-mir`, etc.) pass.
//! The real MIR implementation is planned for a follow-up branch.

/// Run a no-op analysis. Returns an empty string.
///
/// Real implementations will run MIR-level dataflow analysis
/// (beat-alignment, section-segmentation, loudness normalization).
pub fn analyze(_input: &str) -> String {
    String::new()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn smoke() {
        assert_eq!(analyze("anything"), "");
    }
}
