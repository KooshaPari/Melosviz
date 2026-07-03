//! Scene-layer contracts for wgpu visualizations.
//!
//! Scenes are full-screen WGSL layers compiled into [`crate::pipeline::PipelineSet`].
//! The trait keeps scene metadata close to the shader while the renderer stays a
//! simple compositor over compiled pipelines.

use crate::pipeline::{shaders, LayerKind};

/// Metadata contract shared by wgpu scene layers.
pub trait Scene {
    /// Stable layer identifier used for pipeline lookup and tests.
    const KIND: LayerKind;
    /// Human-readable shader/pipeline label.
    const NAME: &'static str;
    /// Vertex count for the draw call. Current scenes use a full-screen triangle.
    const DRAW_VERTICES: u32 = 3;

    /// WGSL source for this scene.
    fn shader_source() -> &'static str;
}

/// B10 conductor scene.
///
/// Draws a central conductor figure and four instrument sections. Stems drive
/// section brightness, beat strength drives the baton pulse, and energy drives
/// the conductor gesture size.
pub struct ConductorScene;

impl Scene for ConductorScene {
    const KIND: LayerKind = LayerKind::Conductor;
    const NAME: &'static str = "conductor";

    fn shader_source() -> &'static str {
        shaders::CONDUCTOR
    }
}
