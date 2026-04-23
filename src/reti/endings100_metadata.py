from __future__ import annotations

from reti.ending_catalog import EndingCatalog

CHAPTERS_100 = {
    "pawn": ("Pawn Endings", "#59A14F"),
    "knight": ("Knight Endings", "#9C755F"),
    "bishop": ("Bishop Endings", "#F28E2B"),
    "rook": ("Rook Endings", "#76B7B2"),
    "rook_minor": ("Rook vs Minor Piece", "#EDC948"),
    "rook_plus": ("Rook + Piece Endings", "#B07AA1"),
    "queen": ("Queen Endings", "#FF9DA7"),
    "minor": ("Minor Piece Endings", "#4E79A7"),
}

_ENDING_ROWS_100: list[tuple[str, str, str, str]] = [
    # (stem, row_id, label, chapter_key)
    ("01_05P", "1-5", "K+P vs K", "pawn"),
    ("06_07RB", "6-7", "R vs B", "rook_minor"),
    ("08_09Rn", "8-9", "R vs N", "rook_minor"),
    ("10Np", "10", "N vs a-Pawn (7th)", "knight"),
    ("10_15Np", "10-15", "N vs P", "knight"),
    ("11Np", "11", "N vs b-Pawn (7th)", "knight"),
    ("12Np", "12", "N vs a-Pawn (6th)", "knight"),
    ("16_19Qp", "16-19", "Q vs P (7th rank)", "queen"),
    ("20Qq", "20", "Q vs Q", "queen"),
    ("21_29Rp", "21-29", "R vs P", "rook"),
    ("30_32Rpp", "30-32", "R vs 2 Connected Pawns", "rook"),
    ("33_36BPb", "33-36", "B+P vs B (same colour)", "bishop"),
    ("37_40BNP", "37-40", "B vs N (+P)", "bishop"),
    ("41_51ocBPPb", "41-51", "Opp-colour B: 2 Connected P", "bishop"),
    ("42_43ocBPPb", "42-43", "Opp-colour B: 2P on 5th", "bishop"),
    ("44_51ocBPPb", "44-51", "Opp-colour B: 2 Isolated P", "bishop"),
    ("52_68RPr", "52-68", "R+P vs R", "rook"),
    ("55RPr", "55", "R+b/g P vs R", "rook"),
    ("56RPr", "56", "R+c/d P vs R", "rook"),
    ("57_58RPr", "57-58", "R+d6 P vs R", "rook"),
    ("65_68RPr", "65-68", "R+a P vs R", "rook"),
    ("69_76RPPr", "69-76", "R+2P vs R", "rook"),
    ("77PP", "77", "Doubled Pawns vs K", "pawn"),
    ("78PP", "78", "Isolated Pawns vs K", "pawn"),
    ("79_81Pp", "79-81", "P vs P (no passed)", "pawn"),
    ("82Pp", "82", "P vs P (both passed)", "pawn"),
    ("83_86PPp", "83-86", "2P vs P (rook's pawn)", "pawn"),
    ("87PPp", "87", "2P vs P (g+h file)", "pawn"),
    ("88PPp", "88", "2P vs P", "pawn"),
    ("93BN", "93", "B+N vs K", "minor"),
    ("94_96RBr", "94-96", "R+B vs R", "rook_plus"),
    ("97RPb", "97", "R+P vs B (6th rank)", "rook_plus"),
    ("98RPb", "98", "R+a P vs B", "rook_plus"),
    ("99Qrp", "99", "Q vs R+b-g P", "queen"),
    ("100Qrp", "100", "Q vs R+a P", "queen"),
]

# Most-specific first. When two endings match the same ply, the earlier
# entry wins. Endings without overlaps are listed last (order irrelevant).
SPECIFICITY_ORDER_100 = [
    # Knight vs Pawn: positional subsets before general
    "10Np",
    "11Np",
    "12Np",
    "10_15Np",
    # R+P vs R: positional subsets before general
    "57_58RPr",
    "55RPr",
    "56RPr",
    "65_68RPr",
    "52_68RPr",
    # Opposite-colour bishops: specific structure before general
    "42_43ocBPPb",
    "44_51ocBPPb",
    "41_51ocBPPb",
    # PP vs P: specific pawn configs before general
    "83_86PPp",
    "87PPp",
    "88PPp",
    # Q vs R+P: a-pawn variant before central-pawn variant
    "100Qrp",
    "99Qrp",
    # R+P vs B: a-pawn variant before 6th-rank variant
    "98RPb",
    "97RPb",
    # Standalone endings (no overlaps)
    "01_05P",
    "06_07RB",
    "08_09Rn",
    "16_19Qp",
    "20Qq",
    "21_29Rp",
    "30_32Rpp",
    "33_36BPb",
    "37_40BNP",
    "69_76RPPr",
    "77PP",
    "78PP",
    "79_81Pp",
    "82Pp",
    "93BN",
    "94_96RBr",
]

ENDINGS_100_CATALOG = EndingCatalog.build(
    name="100endings",
    ending_rows=_ENDING_ROWS_100,
    chapters=CHAPTERS_100,
    specificity_order=SPECIFICITY_ORDER_100,
)
