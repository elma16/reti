from __future__ import annotations

from reti.ending_catalog import Ending, EndingCatalog

# Backward-compatible alias so existing imports still work.
FceEnding = Ending


CHAPTERS = {
    "1": ("Minor Pieces vs King", "#4E79A7"),
    "2": ("Pawn Endings", "#59A14F"),
    "3": ("Knight Endings", "#9C755F"),
    "4": ("Bishop Endings", "#F28E2B"),
    "5": ("Bishop vs Knight", "#E15759"),
    "6": ("Rook Endings", "#76B7B2"),
    "7": ("Rook vs Minor Piece", "#EDC948"),
    "8": ("Rook + Minor Piece", "#B07AA1"),
    "9": ("Queen Endings", "#FF9DA7"),
    "10": ("Queen vs Pieces", "#BAB0AC"),
}

_ENDING_ROWS: list[tuple[str, str, str, str]] = [
    ("1-4BN", "1.4", "Bishop + Knight vs King", "1"),
    ("2-0Pp", "2", "Pawn Endings", "2"),
    ("2-1P", "", "King + Pawn vs King", "2"),
    ("3-1Np", "3.1", "Knight vs Pawns", "3"),
    ("3-2NN", "3.2", "Knight vs Knight", "3"),
    ("4-1Bp", "4.1", "Bishop vs Pawns", "4"),
    ("4-2scBB", "4.2", "Bishop vs Bishop (Same Colour)", "4"),
    ("4-3ocBB", "4.3", "Bishop vs Bishop (Opposite Colour)", "4"),
    ("5-0BN", "5", "Bishop vs Knight", "5"),
    ("6-1-0RP", "6.1", "Rook vs Pawns", "6"),
    ("6-2-0Rr", "6.2", "Rook vs Rook", "6"),
    ("6-2-1RPr", "6.2 A1", "Rook + Pawn vs Rook", "6"),
    ("6-2-2RPPr", "6.2 A2", "Rook + Two Pawns vs Rook", "6"),
    ("6-3RRrr", "6.3", "Two Rooks vs Two Rooks", "6"),
    ("7-1RN", "7.1", "Rook vs Knight", "7"),
    ("7-2RB", "7.2", "Rook vs Bishop", "7"),
    ("8-1RNr", "8.1", "Rook + Knight vs Rook", "8"),
    ("8-2RBr", "8.2", "Rook + Bishop vs Rook", "8"),
    ("8-3RAra", "8.3", "Rook + Minor Piece vs Rook + Minor Piece", "8"),
    ("9-1Qp", "9.1", "Queen vs Pawns", "9"),
    ("9-2Qq", "9.2", "Queen vs Queen", "9"),
    ("9-3QPq", "9.3", "Queen + Pawn vs Queen", "9"),
    ("10-1Qa", "10.1", "Queen vs One Minor Piece", "10"),
    ("10-2Qr", "10.2", "Queen vs Rook", "10"),
    ("10-3Qaa", "10.3", "Queen vs Two Minor Pieces", "10"),
    ("10-4Qra", "10.4", "Queen vs Rook + Minor Piece", "10"),
    ("10-5Qrr", "10.5", "Queen vs Two Rooks", "10"),
    ("10-6Qaaa", "10.6", "Queen vs Three Minor Pieces", "10"),
    ("10-7QAq", "10.7", "Queen and Minor Piece vs Queen", "10"),
    ("10-7-1Qbrr", "", "Queen + Bishop vs Two Rooks", "10"),
]

# Explicit overlap resolution for same-ply matches. Children precede broad parents.
SPECIFICITY_ORDER = [
    "1-4BN",
    "2-1P",
    "2-0Pp",
    "3-1Np",
    "3-2NN",
    "4-1Bp",
    "4-2scBB",
    "4-3ocBB",
    "5-0BN",
    "6-1-0RP",
    "6-2-1RPr",
    "6-2-2RPPr",
    "6-2-0Rr",
    "6-3RRrr",
    "7-1RN",
    "7-2RB",
    "8-1RNr",
    "8-2RBr",
    "8-3RAra",
    "9-1Qp",
    "9-2Qq",
    "9-3QPq",
    "10-1Qa",
    "10-2Qr",
    "10-3Qaa",
    "10-4Qra",
    "10-5Qrr",
    "10-6Qaaa",
    "10-7-1Qbrr",
    "10-7QAq",
]

FCE_CATALOG = EndingCatalog.build(
    name="fce",
    ending_rows=_ENDING_ROWS,
    chapters=CHAPTERS,
    specificity_order=SPECIFICITY_ORDER,
)

# Convenience re-exports used by existing code.
FCE_ENDINGS = FCE_CATALOG.endings
FCE_ENDINGS_BY_STEM = FCE_CATALOG.endings_by_stem
FCE_TABLE_ROWS = tuple(
    (ending.stem, ending.row_id, ending.label) for ending in FCE_ENDINGS
)
