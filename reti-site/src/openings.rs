use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;

use crate::{SiteError, SiteResult};

#[derive(Debug, Clone, Default)]
pub struct OpeningCatalog {
    by_base: BTreeMap<String, OpeningCatalogBase>,
}

#[derive(Debug, Clone, Default)]
struct OpeningCatalogBase {
    names: BTreeSet<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct OpeningOption {
    pub key: String,
    #[serde(rename = "ecoBase")]
    pub eco_base: String,
    #[serde(rename = "ecoGroup")]
    pub eco_group: String,
    pub label: String,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub aliases: Vec<String>,
    #[serde(rename = "totalGames")]
    pub total_games: u64,
}

impl OpeningCatalog {
    pub fn load_optional(path: &Path) -> SiteResult<Self> {
        if !path.is_file() {
            return Ok(Self::default());
        }
        Self::load_csv(path)
    }

    pub fn load_csv(path: &Path) -> SiteResult<Self> {
        let text = fs::read_to_string(path)
            .map_err(|e| SiteError::new(format!("failed to read {}: {e}", path.display())))?;
        Self::parse_csv(&text)
    }

    pub fn parse_csv(text: &str) -> SiteResult<Self> {
        let mut lines = text.lines();
        let header = lines
            .next()
            .ok_or_else(|| SiteError::new("opening catalog CSV is empty"))?;
        let headers = parse_csv_line(header);
        let idx = |name: &str| {
            headers
                .iter()
                .position(|field| field == name)
                .ok_or_else(|| {
                    SiteError::new(format!("opening catalog CSV missing {name:?} column"))
                })
        };
        let eco_base_idx = idx("eco_base")?;
        let name_idx = idx("name")?;
        let mut by_base: BTreeMap<String, OpeningCatalogBase> = BTreeMap::new();
        for line in lines {
            if line.trim().is_empty() {
                continue;
            }
            let cells = parse_csv_line(line);
            if cells.len() <= eco_base_idx || cells.len() <= name_idx {
                continue;
            }
            let eco_base = normalize_eco_base(&cells[eco_base_idx]);
            if eco_base == "unknown" {
                continue;
            }
            let name = cells[name_idx].trim();
            if name.is_empty() {
                continue;
            }
            by_base
                .entry(eco_base)
                .or_default()
                .names
                .insert(name.to_string());
        }
        Ok(Self { by_base })
    }

    pub fn option_for_base(&self, eco_base: &str, total_games: u64) -> OpeningOption {
        let names = self
            .by_base
            .get(eco_base)
            .map(|entry| entry.names.iter().cloned().collect::<Vec<_>>())
            .unwrap_or_default();
        let label = names
            .iter()
            .min_by_key(|name| (name.len(), name.as_str()))
            .cloned()
            .unwrap_or_else(|| eco_base.to_string());
        let aliases = names
            .into_iter()
            .filter(|name| name != &label)
            .take(24)
            .collect();
        OpeningOption {
            key: format!("eco:{eco_base}"),
            eco_base: eco_base.to_string(),
            eco_group: eco_base
                .chars()
                .next()
                .filter(|ch| matches!(ch, 'A'..='E'))
                .map(|ch| ch.to_string())
                .unwrap_or_else(|| "unknown".to_string()),
            label,
            aliases,
            total_games,
        }
    }
}

pub fn normalize_eco_base(raw: &str) -> String {
    let raw = raw.trim();
    if raw.len() < 3 {
        return "unknown".to_string();
    }
    let mut chars = raw.chars();
    let Some(family) = chars.next().map(|ch| ch.to_ascii_uppercase()) else {
        return "unknown".to_string();
    };
    let Some(d1) = chars.next() else {
        return "unknown".to_string();
    };
    let Some(d2) = chars.next() else {
        return "unknown".to_string();
    };
    if !matches!(family, 'A'..='E') || !d1.is_ascii_digit() || !d2.is_ascii_digit() {
        return "unknown".to_string();
    }
    format!("{family}{d1}{d2}")
}

fn parse_csv_line(line: &str) -> Vec<String> {
    let mut cells = Vec::new();
    let mut current = String::new();
    let mut chars = line.chars().peekable();
    let mut in_quotes = false;
    while let Some(ch) = chars.next() {
        match ch {
            '"' if in_quotes && chars.peek() == Some(&'"') => {
                current.push('"');
                chars.next();
            }
            '"' => in_quotes = !in_quotes,
            ',' if !in_quotes => {
                cells.push(current);
                current = String::new();
            }
            _ => current.push(ch),
        }
    }
    cells.push(current);
    cells
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_csv_with_quoted_opening_names() {
        let catalog = OpeningCatalog::parse_csv(
            "row_number,eco,eco_base,eco_group,name,moves,source_url\n1,A00q,A00,A,\"Polish, 1...d5\",1.b4 d5,x\n2,E99,E99,E,King's Indian,1.d4,x\n",
        )
        .unwrap();
        let option = catalog.option_for_base("A00", 10);
        assert_eq!(option.key, "eco:A00");
        assert_eq!(option.label, "Polish, 1...d5");
    }

    #[test]
    fn normalizes_extended_codes_to_base() {
        assert_eq!(normalize_eco_base("a00q"), "A00");
        assert_eq!(normalize_eco_base("E99"), "E99");
        assert_eq!(normalize_eco_base("Z99"), "unknown");
    }
}
