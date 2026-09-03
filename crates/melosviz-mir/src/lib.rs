// melosviz-mir stub library — see src/bin/main.rs for the CLI.
// The real MIR analyzer will land in follow-up PRs once the production
// wgpu renderer is in place.

pub fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}
