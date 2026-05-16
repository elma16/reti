use serde::Serialize;
use std::collections::BTreeSet;

#[derive(Debug, Clone, Copy, Serialize)]
pub struct Chapter {
    pub key: &'static str,
    pub label: &'static str,
    pub color: &'static str,
}

#[derive(Debug, Clone, Copy, Serialize)]
pub struct Ending {
    pub stem: &'static str,
    #[serde(rename = "rowId")]
    pub row_id: &'static str,
    pub label: &'static str,
    #[serde(rename = "displayLabel")]
    pub display_label: &'static str,
    #[serde(rename = "chapterKey")]
    pub chapter_key: &'static str,
    #[serde(rename = "chapterLabel")]
    pub chapter_label: &'static str,
    pub color: &'static str,
}

pub const CHAPTERS: &[Chapter] = &[
    Chapter {
        key: "1",
        label: "Minor Pieces vs King",
        color: "#4E79A7",
    },
    Chapter {
        key: "2",
        label: "Pawn Endings",
        color: "#59A14F",
    },
    Chapter {
        key: "3",
        label: "Knight Endings",
        color: "#9C755F",
    },
    Chapter {
        key: "4",
        label: "Bishop Endings",
        color: "#F28E2B",
    },
    Chapter {
        key: "5",
        label: "Bishop vs Knight",
        color: "#E15759",
    },
    Chapter {
        key: "6",
        label: "Rook Endings",
        color: "#76B7B2",
    },
    Chapter {
        key: "7",
        label: "Rook vs Minor Piece",
        color: "#EDC948",
    },
    Chapter {
        key: "8",
        label: "Rook + Minor Piece",
        color: "#B07AA1",
    },
    Chapter {
        key: "9",
        label: "Queen Endings",
        color: "#FF9DA7",
    },
    Chapter {
        key: "10",
        label: "Queen vs Pieces",
        color: "#BAB0AC",
    },
];

pub const ENDINGS: &[Ending] = &[
    ending("1-4BN", "1.4", "Bishop + Knight vs King", "1"),
    ending("2-0Pp", "2", "Pawn Endings", "2"),
    ending("2-1P", "", "King + Pawn vs King", "2"),
    ending("3-1Np", "3.1", "Knight vs Pawns", "3"),
    ending("3-2NN", "3.2", "Knight vs Knight", "3"),
    ending("4-1Bp", "4.1", "Bishop vs Pawns", "4"),
    ending("4-2scBB", "4.2", "Bishop vs Bishop (Same Colour)", "4"),
    ending("4-3ocBB", "4.3", "Bishop vs Bishop (Opposite Colour)", "4"),
    ending("5-0BN", "5", "Bishop vs Knight", "5"),
    ending("6-1-0RP", "6.1", "Rook vs Pawns", "6"),
    ending("6-2-0Rr", "6.2", "Rook vs Rook", "6"),
    ending("6-2-1RPr", "6.2 A1", "Rook + Pawn vs Rook", "6"),
    ending("6-2-2RPPr", "6.2 A2", "Rook + Two Pawns vs Rook", "6"),
    ending("6-3RRrr", "6.3", "Two Rooks vs Two Rooks", "6"),
    ending("7-1RN", "7.1", "Rook vs Knight", "7"),
    ending("7-2RB", "7.2", "Rook vs Bishop", "7"),
    ending("8-1RNr", "8.1", "Rook + Knight vs Rook", "8"),
    ending("8-2RBr", "8.2", "Rook + Bishop vs Rook", "8"),
    ending(
        "8-3RAra",
        "8.3",
        "Rook + Minor Piece vs Rook + Minor Piece",
        "8",
    ),
    ending("9-1Qp", "9.1", "Queen vs Pawns", "9"),
    ending("9-2Qq", "9.2", "Queen vs Queen", "9"),
    ending("9-3QPq", "9.3", "Queen + Pawn vs Queen", "9"),
    ending("10-1Qa", "10.1", "Queen vs One Minor Piece", "10"),
    ending("10-2Qr", "10.2", "Queen vs Rook", "10"),
    ending("10-3Qaa", "10.3", "Queen vs Two Minor Pieces", "10"),
    ending("10-4Qra", "10.4", "Queen vs Rook + Minor Piece", "10"),
    ending("10-5Qrr", "10.5", "Queen vs Two Rooks", "10"),
    ending("10-6Qaaa", "10.6", "Queen vs Three Minor Pieces", "10"),
    ending("10-7QAq", "10.7", "Queen and Minor Piece vs Queen", "10"),
    ending("10-7-1Qbrr", "", "Queen + Bishop vs Two Rooks", "10"),
];

const fn ending(
    stem: &'static str,
    row_id: &'static str,
    label: &'static str,
    chapter_key: &'static str,
) -> Ending {
    let chapter = chapter_for(chapter_key);
    Ending {
        stem,
        row_id,
        label,
        display_label: label,
        chapter_key,
        chapter_label: chapter.label,
        color: chapter.color,
    }
}

const fn chapter_for(key: &'static str) -> Chapter {
    let mut idx = 0;
    while idx < CHAPTERS.len() {
        if str_eq(CHAPTERS[idx].key, key) {
            return CHAPTERS[idx];
        }
        idx += 1;
    }
    CHAPTERS[0]
}

const fn str_eq(a: &str, b: &str) -> bool {
    let a = a.as_bytes();
    let b = b.as_bytes();
    if a.len() != b.len() {
        return false;
    }
    let mut idx = 0;
    while idx < a.len() {
        if a[idx] != b[idx] {
            return false;
        }
        idx += 1;
    }
    true
}

pub const AUXILIARY: &[(&str, &str, &str)] = &[
    ("6-2-2RPPrConnected", "6-2-2RPPr", "Connected pawns"),
    ("8-1RNrNoPawns", "8-1RNr", "Without pawns"),
    ("8-2RBrNoPawns", "8-2RBr", "Without pawns"),
    ("10-2QrNoPawns", "10-2Qr", "Without pawns"),
    ("10-7-1QbrrNoPawns", "10-7-1Qbrr", "Without pawns"),
];

pub fn known_stems() -> BTreeSet<String> {
    ENDINGS
        .iter()
        .map(|ending| ending.stem.to_string())
        .chain(AUXILIARY.iter().map(|(stem, _, _)| stem.to_string()))
        .collect()
}

pub fn aux_parent(stem: &str) -> Option<&'static str> {
    AUXILIARY
        .iter()
        .find(|(child, _, _)| *child == stem)
        .map(|(_, parent, _)| *parent)
}

pub fn aux_label(stem: &str) -> Option<&'static str> {
    AUXILIARY
        .iter()
        .find(|(child, _, _)| *child == stem)
        .map(|(_, _, label)| *label)
}

pub fn ending_by_stem(stem: &str) -> Option<Ending> {
    ENDINGS.iter().copied().find(|ending| ending.stem == stem)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn catalog_has_30_canonical_rows() {
        assert_eq!(ENDINGS.len(), 30);
        assert!(known_stems().contains("10-7-1QbrrNoPawns"));
    }
}
