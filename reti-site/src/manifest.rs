use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fs;
use std::io::Read;
use std::path::Path;
use std::time::UNIX_EPOCH;

use crate::{SiteError, SiteResult};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FileSignature {
    pub path: String,
    #[serde(rename = "sizeBytes")]
    pub size_bytes: u64,
    #[serde(rename = "mtimeNs")]
    pub mtime_ns: u128,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub sha256: Option<String>,
}

pub fn file_signature(path: &Path, include_hash: bool) -> SiteResult<FileSignature> {
    let meta = fs::metadata(path)
        .map_err(|e| SiteError::new(format!("failed to stat {}: {e}", path.display())))?;
    let mtime_ns = meta
        .modified()
        .ok()
        .and_then(|time| time.duration_since(UNIX_EPOCH).ok())
        .map(|duration| duration.as_nanos())
        .unwrap_or(0);
    Ok(FileSignature {
        path: path.to_string_lossy().into_owned(),
        size_bytes: meta.len(),
        mtime_ns,
        sha256: if include_hash {
            Some(sha256_file(path)?)
        } else {
            None
        },
    })
}

pub fn sha256_file(path: &Path) -> SiteResult<String> {
    let mut file = fs::File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 1024 * 1024];
    loop {
        let n = file.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(hex::encode(hasher.finalize()))
}

pub fn fingerprint(value: &Value) -> SiteResult<String> {
    let mut clone = value.clone();
    if let Some(object) = clone.as_object_mut() {
        object.remove("fingerprint");
    }
    let encoded = serde_json::to_vec(&clone)?;
    let mut hasher = Sha256::new();
    hasher.update(encoded);
    Ok(hex::encode(hasher.finalize()))
}

pub fn base_manifest(
    title: &str,
    annotated_run_dir: &Path,
    source_totals_json: &Path,
    syzygy_dirs: &[std::path::PathBuf],
    pgn_utils_bin: &Path,
    thresholds: &[u32],
    tablebase_threshold: u32,
) -> SiteResult<Value> {
    let syzygy: Vec<Value> = syzygy_dirs
        .iter()
        .map(|dir| {
            let mut file_count = 0u64;
            let mut size_bytes = 0u64;
            if let Ok(entries) = fs::read_dir(dir) {
                for entry in entries.flatten() {
                    if let Ok(meta) = entry.metadata() {
                        if meta.is_file() {
                            file_count += 1;
                            size_bytes += meta.len();
                        }
                    }
                }
            }
            json!({
                "path": dir.to_string_lossy(),
                "fileCount": file_count,
                "sizeBytes": size_bytes,
            })
        })
        .collect();
    let mut manifest = json!({
        "schemaVersion": 2,
        "builder": "reti-site",
        "kind": "fce-combined-tablebase-snapshot",
        "settings": {
            "title": title,
            "annotatedRunDir": annotated_run_dir.to_string_lossy(),
            "sourceTotalsJson": source_totals_json.to_string_lossy(),
            "thresholds": thresholds,
            "tablebaseThreshold": tablebase_threshold,
            "countingSemantics": "first-run-per-game-stem",
            "positionSelection": "first-marker-per-game-stem",
            "thresholdSemantics": "first-stem-run-length",
            "evaluation": "syzygy-wdl-le-5",
            "evaluationEngine": "rust-shakmaty-syzygy",
            "actualResultSemantics": "all qualifying game-ending incidences from named-material perspective",
            "tablebaseResultCrosstab": "tablebase-eligible first markers only",
            "syzygyDirs": syzygy,
        },
        "inputs": {
            "summaryCsv": file_signature(&annotated_run_dir.join("summary.csv"), true)?,
            "sourceTotalsJson": file_signature(source_totals_json, true)?,
            "pgnUtilsBin": file_signature(pgn_utils_bin, false).ok(),
        }
    });
    let fp = fingerprint(&manifest)?;
    manifest["fingerprint"] = Value::String(fp);
    Ok(manifest)
}

pub fn manifest_matches(path: &Path, expected: &Value) -> bool {
    let Ok(text) = fs::read_to_string(path) else {
        return false;
    };
    let Ok(actual) = serde_json::from_str::<Value>(&text) else {
        return false;
    };
    actual == *expected
}
