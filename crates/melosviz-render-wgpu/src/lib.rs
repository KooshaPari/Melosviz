//! Melosviz wgpu Render — stub crate.
//!
//! This is a no-op placeholder so that workspace-level CI checks
//! (`cargo build -p melosviz-render-wgpu`, license scanning, etc.) pass.
//! The real wgpu renderer is planned for a follow-up branch.

/// Returns true when the wgpu renderer is initialized.
///
/// Real implementations will request an adapter/device and
/// allocate GPU buffers for frame rendering.
pub fn is_initialized() -> bool {
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn smoke() {
        assert!(!is_initialized());
    }
}
