//! Incremental segment cache — re-render only dirty segments on edit.
//!
//! An edit (palette change, beat gain, segment label) typically touches
//! parameters in one or a few segments.  The cache stores rendered frame
//! ranges keyed by `(segment_id, parameter_hash)`:
//!
//! ```text
//! edit event
//!   → identify changed parameter range [t_start, t_end]
//!   → mark dirty segments D ⊆ scene_segments
//!   → for s in D: evict cache[s.id]
//!   → re-render only D → store Arc<Vec<RgbFrame>> in cache
//!   → splice into output
//! ```
//!
//! Expected edit latency: 30 s segment × 30 fps × ~3 ms/frame (estimated)
//! ≈ 2.7 s — well under the 5 s/edit target (see `docs/PERF_BENCHMARK.md §4`).
//!
//! The cache deliberately avoids holding `wgpu::Texture` directly because
//! textures are device-local and cannot be `Send`.  Instead it stores
//! `Arc<Vec<u8>>` (raw RGB24 bytes) which can be cheaply re-uploaded to a
//! new `wgpu::Buffer` without the borrow-checker complexity of sharing
//! device resources across threads.

use ahash::AHashMap;
use std::sync::Arc;

/// Cache key: segment id + deterministic hash of the parameters that affect it.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct SegmentKey {
    /// Segment id (e.g. "segment_0", "verse_1").
    pub segment_id: String,
    /// FNV/ahash of the segment's relevant RenderSpec parameters so a
    /// parameter change automatically invalidates the entry.
    pub param_hash: u64,
}

impl SegmentKey {
    /// Construct a `SegmentKey` from a segment id and a pre-computed parameter hash.
    pub fn new(segment_id: impl Into<String>, param_hash: u64) -> Self {
        Self { segment_id: segment_id.into(), param_hash }
    }
}

/// A cached rendered segment: raw RGB24 bytes for every frame in the segment.
///
/// `Arc<Vec<u8>>` allows cheap cloning and sharing across the preview and
/// export paths without copying pixel data.
pub type RenderedSegment = Arc<Vec<u8>>;

/// Per-segment incremental render cache.
///
/// Thread-safety: the cache itself is `!Send` because it is single-threaded
/// (the wgpu command encoder is not `Send`).  Wrap in a `Mutex<SegmentCache>`
/// if cross-thread access is needed.
#[derive(Default)]
pub struct SegmentCache {
    entries: AHashMap<SegmentKey, RenderedSegment>,
    /// Total RGB24 bytes currently held in the cache (for memory budgeting).
    total_bytes: usize,
}

impl SegmentCache {
    /// Create an empty cache.
    pub fn new() -> Self {
        Self::default()
    }

    /// Insert a rendered segment into the cache.
    ///
    /// If an entry with the same `key` already exists, it is replaced and
    /// the old memory is released (Arc ref-count drops).
    pub fn insert(&mut self, key: SegmentKey, data: Vec<u8>) {
        let bytes = data.len();
        if let Some(old) = self.entries.insert(key, Arc::new(data)) {
            self.total_bytes = self.total_bytes.saturating_sub(old.len());
        }
        self.total_bytes += bytes;
    }

    /// Look up a cached segment, returning a clone of the `Arc` (zero-copy).
    pub fn get(&self, key: &SegmentKey) -> Option<RenderedSegment> {
        self.entries.get(key).cloned()
    }

    /// Evict all entries whose `segment_id` matches `id`.
    ///
    /// Used when a segment's parameters change (any `param_hash` for that id
    /// is now stale).
    pub fn evict_segment(&mut self, segment_id: &str) {
        self.entries.retain(|k, v| {
            if k.segment_id == segment_id {
                self.total_bytes = self.total_bytes.saturating_sub(v.len());
                false
            } else {
                true
            }
        });
    }

    /// Evict a single entry by exact key.
    pub fn evict(&mut self, key: &SegmentKey) {
        if let Some(old) = self.entries.remove(key) {
            self.total_bytes = self.total_bytes.saturating_sub(old.len());
        }
    }

    /// Clear all cached entries.
    pub fn clear(&mut self) {
        self.entries.clear();
        self.total_bytes = 0;
    }

    /// Number of cached segments.
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    /// True if the cache is empty.
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// Total RGB24 bytes held in the cache.
    pub fn total_bytes(&self) -> usize {
        self.total_bytes
    }

    /// Compute a parameter hash for a segment given its key parameters.
    ///
    /// Called by the renderer before each segment render to decide whether
    /// the cache entry is still valid.  Hashes `label`, `palette_index`,
    /// `scene_type`, and the first/last `energy` keyframe values for the
    /// segment's time range.
    pub fn compute_param_hash(
        label: &str,
        palette_index: usize,
        scene_type: &str,
        energy_first: f32,
        energy_last: f32,
    ) -> u64 {
        use std::collections::hash_map::DefaultHasher;
        use std::hash::{Hash, Hasher};
        let mut h = DefaultHasher::new();
        label.hash(&mut h);
        palette_index.hash(&mut h);
        scene_type.hash(&mut h);
        // f32 → bit pattern for deterministic hashing
        energy_first.to_bits().hash(&mut h);
        energy_last.to_bits().hash(&mut h);
        h.finish()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_data(n: usize) -> Vec<u8> {
        vec![42u8; n]
    }

    #[test]
    fn test_insert_and_get() {
        let mut cache = SegmentCache::new();
        let key = SegmentKey::new("seg_0", 1234);
        cache.insert(key.clone(), make_data(100));
        let got = cache.get(&key).expect("entry should be present");
        assert_eq!(got.len(), 100);
        assert_eq!(got[0], 42);
    }

    #[test]
    fn test_get_missing_returns_none() {
        let cache = SegmentCache::new();
        assert!(cache.get(&SegmentKey::new("seg_0", 0)).is_none());
    }

    #[test]
    fn test_insert_replaces_existing() {
        let mut cache = SegmentCache::new();
        let key = SegmentKey::new("seg_0", 1);
        cache.insert(key.clone(), make_data(100));
        cache.insert(key.clone(), make_data(200));
        let got = cache.get(&key).expect("should exist");
        assert_eq!(got.len(), 200);
    }

    #[test]
    fn test_evict_segment_removes_all_hashes_for_id() {
        let mut cache = SegmentCache::new();
        cache.insert(SegmentKey::new("seg_0", 1), make_data(10));
        cache.insert(SegmentKey::new("seg_0", 2), make_data(10));
        cache.insert(SegmentKey::new("seg_1", 1), make_data(10));
        cache.evict_segment("seg_0");
        assert!(cache.get(&SegmentKey::new("seg_0", 1)).is_none());
        assert!(cache.get(&SegmentKey::new("seg_0", 2)).is_none());
        // seg_1 should still be present
        assert!(cache.get(&SegmentKey::new("seg_1", 1)).is_some());
    }

    #[test]
    fn test_evict_exact_key() {
        let mut cache = SegmentCache::new();
        let k1 = SegmentKey::new("seg_0", 1);
        let k2 = SegmentKey::new("seg_0", 2);
        cache.insert(k1.clone(), make_data(10));
        cache.insert(k2.clone(), make_data(10));
        cache.evict(&k1);
        assert!(cache.get(&k1).is_none());
        assert!(cache.get(&k2).is_some());
    }

    #[test]
    fn test_clear() {
        let mut cache = SegmentCache::new();
        cache.insert(SegmentKey::new("seg_0", 1), make_data(50));
        cache.insert(SegmentKey::new("seg_1", 2), make_data(50));
        cache.clear();
        assert!(cache.is_empty());
        assert_eq!(cache.total_bytes(), 0);
    }

    #[test]
    fn test_total_bytes_tracking() {
        let mut cache = SegmentCache::new();
        assert_eq!(cache.total_bytes(), 0);
        cache.insert(SegmentKey::new("seg_0", 1), make_data(300));
        assert_eq!(cache.total_bytes(), 300);
        cache.insert(SegmentKey::new("seg_1", 1), make_data(200));
        assert_eq!(cache.total_bytes(), 500);
        cache.evict_segment("seg_0");
        assert_eq!(cache.total_bytes(), 200);
    }

    #[test]
    fn test_total_bytes_replace_updates_correctly() {
        let mut cache = SegmentCache::new();
        let key = SegmentKey::new("seg_0", 1);
        cache.insert(key.clone(), make_data(100));
        cache.insert(key.clone(), make_data(200));
        assert_eq!(cache.total_bytes(), 200);
    }

    #[test]
    fn test_len_and_is_empty() {
        let mut cache = SegmentCache::new();
        assert!(cache.is_empty());
        cache.insert(SegmentKey::new("s", 1), make_data(1));
        assert_eq!(cache.len(), 1);
        assert!(!cache.is_empty());
    }

    #[test]
    fn test_compute_param_hash_deterministic() {
        let h1 = SegmentCache::compute_param_hash("chorus", 2, "beat_reactive", 0.8, 0.9);
        let h2 = SegmentCache::compute_param_hash("chorus", 2, "beat_reactive", 0.8, 0.9);
        assert_eq!(h1, h2);
    }

    #[test]
    fn test_compute_param_hash_differs_on_label_change() {
        let h1 = SegmentCache::compute_param_hash("chorus", 2, "beat_reactive", 0.8, 0.9);
        let h2 = SegmentCache::compute_param_hash("verse", 2, "beat_reactive", 0.8, 0.9);
        assert_ne!(h1, h2, "different labels should produce different hashes");
    }

    #[test]
    fn test_compute_param_hash_differs_on_energy_change() {
        let h1 = SegmentCache::compute_param_hash("chorus", 2, "beat_reactive", 0.8, 0.9);
        let h2 = SegmentCache::compute_param_hash("chorus", 2, "beat_reactive", 0.5, 0.9);
        assert_ne!(h1, h2, "different energy values should produce different hashes");
    }

    #[test]
    fn test_arc_clone_is_zero_copy() {
        let mut cache = SegmentCache::new();
        let key = SegmentKey::new("seg_0", 1);
        let data = make_data(1_000_000);
        cache.insert(key.clone(), data);
        // Clone the Arc — should not allocate new pixel memory
        let a = cache.get(&key).unwrap();
        let b = cache.get(&key).unwrap();
        assert!(Arc::ptr_eq(&a, &b), "get() should return clones of the same Arc");
    }
}
