# CQL 6.2 Unicode Syntax Incompatibilities

CQL 6.2 introduced Unicode operator aliases. These are not recognized by CQL 6.1
and cause `return code 1` failures. This document lists all occurrences found in
this repo and their ASCII (6.1-compatible) equivalents.

## Unicode-to-ASCII Mapping

| Unicode | Codepoint | ASCII (6.1) | Meaning |
|---------|-----------|-------------|---------|
| `⬓`    | U+2B13    | `flipcolor` | Color-flip transform |
| `✵`    | U+2735    | `flip`      | Dihedral (8-way) transform |
| `――`   | U+2015x2  | `--`        | Move (non-capture) |
| `×`    | U+00D7    | `[x]`       | Capture |
| `→`    | U+2192    | `->`        | Attacks arrow |
| `←`    | U+2190    | `<-`        | Attacked-by arrow |
| `⊢`    | U+22A2    | `path`      | Path filter |
| `◎`    | U+25CE    | `focus`     | Focus (path restriction) |
| `∊`    | U+220A    | `element`   | Element iteration |
| `♔♕♖♗♘♙` | —      | `KQRBNP`    | White pieces |
| `♚♛♜♝♞♟` | —      | `kqrbnp`    | Black pieces |
| `△`    | U+25B3    | `A`         | Any white piece |
| `▲`    | U+25B2    | `a`         | Any black piece |
| `◭`    | U+25ED    | `[Aa]`      | Any piece (either color) |
| `□`    | U+25A1    | `_`         | Empty square |
| `▦`    | U+25A6    | `[a-h1-8]`  | All squares |

## Affected Files (38 total)

### `cql-files/100endings/` (3 files) — `⬓` only

- `41_51ocBPPb.cql`
- `42_43ocBPPb.cql`
- `44_51ocBPPb.cql`

### `cql-files/mates/` (28 files) — `⬓` only

- `BN.cql`, `KBB.cql`, `KNN.cql`, `anastasiamate.cql`, `anderssen.cql`,
  `arabianmate.cql`, `backrankmate.cql`, `balestramate.cql`,
  `blackburnemate.cql`, `blindswinemate.cql`, `bodenmate.cql`,
  `castlingmate.cql`, `damianobishopmate.cql`, `davidandgoliath.cql`,
  `greco.cql`, `hookmate.cql`, `ismate.cql`, `killbox.cql`,
  `laddermate.cql`, `maxlangemate.cql`, `mayet.cql`, `morphymate.cql`,
  `opera.cql`, `pillsbury.cql`, `queen.cql`, `retimate.cql`,
  `rookmate.cql`, `smotheredmate.cql`, `suffocationmate.cql`,
  `swallowtail.cql`, `trianglemate.cql`, `twobishopmate.cql`,
  `twoknightmate.cql`

### `cql-files/silly/` (6 files) — mixed Unicode operators

- `abcd.cql` — `×`
- `doublecheck.cql` — `→`
- `doublecheckANDmate.cql` — `→`
- `elasticband.cql` — `×`, `⊢`
- `fischer.cql` — `×`, `――`, `⊢`, `♗`, `♘`, `♚`, `♟`
- `rookhomerun.cql` — `――`, `⊢`, `◎`, `✵`, `∊`, `♖` (self-declared 6.2-only)
