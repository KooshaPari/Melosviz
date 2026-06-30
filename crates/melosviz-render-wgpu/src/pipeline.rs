//! Render pipeline definitions — one `wgpu::RenderPipeline` per visual layer.
//!
//! Each layer corresponds to a WGSL shader that implements one aspect of
//! the MelosViz visual vocabulary:
//!
//! | Layer | Shader | Visual |
//! |-------|--------|--------|
//! | `BgGradient` | `bg_gradient.wgsl` | segment-label → world background colour |
//! | `BeatPulse` | `beat_pulse.wgsl` | energy → emitter scale + radial glow |
//! | `SpectralHue` | `spectral_hue.wgsl` | spectral_centroid → HSV hue rotation |
//! | `StemParticles` | `stem_particles.wgsl` | drums → particle density, bass → scale |
//!
//! Pipelines are lazy-built on first use and stored in [`PipelineSet`].

use anyhow::Result;

/// Identifies which visual layer pipeline to use.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum LayerKind {
    /// Solid/gradient background driven by segment label colour.
    BgGradient,
    /// Radial emitter glow driven by beat energy.
    BeatPulse,
    /// Full-screen HSV hue rotation driven by spectral centroid.
    SpectralHue,
    /// Particle system driven by drum/bass stems.
    StemParticles,
}

/// WGSL shader source strings embedded at compile time.
pub mod shaders {
    pub const BG_GRADIENT: &str = include_str!("shaders/bg_gradient.wgsl");
    pub const BEAT_PULSE: &str = include_str!("shaders/beat_pulse.wgsl");
    pub const SPECTRAL_HUE: &str = include_str!("shaders/spectral_hue.wgsl");
    pub const STEM_PARTICLES: &str = include_str!("shaders/stem_particles.wgsl");
}

/// Container for all compiled render pipelines.
///
/// [`PipelineSet::build`] compiles all four layer shaders.  On GPU
/// environments this takes ~200 ms for the first compile (Metal PSO
/// compilation); subsequent runs use the shader cache.
pub struct PipelineSet {
    pub bg_gradient: wgpu::RenderPipeline,
    pub beat_pulse: wgpu::RenderPipeline,
    pub spectral_hue: wgpu::RenderPipeline,
    pub stem_particles: wgpu::RenderPipeline,
    pub uniform_bind_group_layout: wgpu::BindGroupLayout,
}

impl PipelineSet {
    /// Compile all render pipelines for the given device and output format.
    ///
    /// `output_format` must match the swapchain format (for preview) or
    /// `wgpu::TextureFormat::Rgba8Unorm` (for headless export).
    pub fn build(device: &wgpu::Device, output_format: wgpu::TextureFormat) -> Result<Self> {
        // Uniform bind group layout — one uniform buffer at binding 0.
        let uniform_bind_group_layout =
            device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
                label: Some("melosviz_uniform_bgl"),
                entries: &[wgpu::BindGroupLayoutEntry {
                    binding: 0,
                    visibility: wgpu::ShaderStages::VERTEX | wgpu::ShaderStages::FRAGMENT,
                    ty: wgpu::BindingType::Buffer {
                        ty: wgpu::BufferBindingType::Uniform,
                        has_dynamic_offset: false,
                        min_binding_size: None,
                    },
                    count: None,
                }],
            });

        let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("melosviz_pipeline_layout"),
            bind_group_layouts: &[&uniform_bind_group_layout],
            push_constant_ranges: &[],
        });

        let build_pipeline = |label: &str, shader_src: &str| {
            let module = device.create_shader_module(wgpu::ShaderModuleDescriptor {
                label: Some(label),
                source: wgpu::ShaderSource::Wgsl(shader_src.into()),
            });
            device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
                label: Some(label),
                layout: Some(&pipeline_layout),
                vertex: wgpu::VertexState {
                    module: &module,
                    entry_point: Some("vs_main"),
                    buffers: &[],
                    compilation_options: Default::default(),
                },
                fragment: Some(wgpu::FragmentState {
                    module: &module,
                    entry_point: Some("fs_main"),
                    targets: &[Some(wgpu::ColorTargetState {
                        format: output_format,
                        blend: Some(wgpu::BlendState {
                            color: wgpu::BlendComponent {
                                src_factor: wgpu::BlendFactor::SrcAlpha,
                                dst_factor: wgpu::BlendFactor::OneMinusSrcAlpha,
                                operation: wgpu::BlendOperation::Add,
                            },
                            alpha: wgpu::BlendComponent::OVER,
                        }),
                        write_mask: wgpu::ColorWrites::ALL,
                    })],
                    compilation_options: Default::default(),
                }),
                primitive: wgpu::PrimitiveState {
                    topology: wgpu::PrimitiveTopology::TriangleList,
                    ..Default::default()
                },
                depth_stencil: None,
                multisample: wgpu::MultisampleState::default(),
                multiview: None,
                cache: None,
            })
        };

        Ok(Self {
            bg_gradient: build_pipeline("bg_gradient", shaders::BG_GRADIENT),
            beat_pulse: build_pipeline("beat_pulse", shaders::BEAT_PULSE),
            spectral_hue: build_pipeline("spectral_hue", shaders::SPECTRAL_HUE),
            stem_particles: build_pipeline("stem_particles", shaders::STEM_PARTICLES),
            uniform_bind_group_layout,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_shader_sources_are_non_empty() {
        // Verify that all WGSL shader files are embedded and non-empty at compile time.
        assert!(!shaders::BG_GRADIENT.is_empty(), "bg_gradient.wgsl must be non-empty");
        assert!(!shaders::BEAT_PULSE.is_empty(), "beat_pulse.wgsl must be non-empty");
        assert!(!shaders::SPECTRAL_HUE.is_empty(), "spectral_hue.wgsl must be non-empty");
        assert!(!shaders::STEM_PARTICLES.is_empty(), "stem_particles.wgsl must be non-empty");
    }

    #[test]
    fn test_shader_sources_contain_entry_points() {
        // Each shader must declare vs_main and fs_main entry points.
        for (name, src) in [
            ("bg_gradient", shaders::BG_GRADIENT),
            ("beat_pulse", shaders::BEAT_PULSE),
            ("spectral_hue", shaders::SPECTRAL_HUE),
            ("stem_particles", shaders::STEM_PARTICLES),
        ] {
            assert!(src.contains("vs_main"), "{name}: missing vs_main entry point");
            assert!(src.contains("fs_main"), "{name}: missing fs_main entry point");
        }
    }

    #[test]
    fn test_shader_sources_reference_frame_uniforms() {
        // Each shader must use the FrameUniforms struct (keeps spec→shader contract).
        for (name, src) in [
            ("bg_gradient", shaders::BG_GRADIENT),
            ("beat_pulse", shaders::BEAT_PULSE),
            ("spectral_hue", shaders::SPECTRAL_HUE),
            ("stem_particles", shaders::STEM_PARTICLES),
        ] {
            assert!(
                src.contains("FrameUniforms"),
                "{name}: shader must reference FrameUniforms struct"
            );
        }
    }

    #[test]
    fn test_layer_kind_is_copy() {
        let a = LayerKind::BeatPulse;
        let _b = a;  // Copy means no move — would fail to compile if not Copy
        let _c = a;
    }
}
