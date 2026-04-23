# CQL command-line comparison: CQL 6.1 vs CQL 6.2 vs CQLi 1.0.6

This document compares the command-line interfaces of three CQL implementations
used in this project. The goal is to identify where they align and where they
diverge, so that `analyse_cql.py` can safely pass flags to any of them.

Sources:

- **CQL 6.1**: `cql-bin/cql6-1/cql --help` and https://www.gadycosteff.com/cql-6-1/options.html
- **CQL 6.2**: `cql-bin/cql6-2/cql --help` and https://www.gadycosteff.com/cql/options.html
- **CQLi 1.0.6**: `cql-bin/cqli-1.0.6-macos/cqli-arm64 --help` and the bundled `manual.pdf`

## Flag syntax

| | CQL 6.1 | CQL 6.2 | CQLi 1.0.6 |
|---|---|---|---|
| Prefix style | Single `-` only (e.g. `-input`) | Single `-` only (e.g. `-input`) | Single `-` or double `--` (e.g. `-i` / `--input`); case-insensitive |
| Short flags | `-i`, `-o`, `-g`, `-s` | `-i`, `-o`, `-g`, `-s` | `-i`, `-o`, `-g`, `-s`, `-h`, `-a`, `-w` |
| CQL file position | Last argument | Last argument | Last argument |
| Comment syntax in `.cql` files | `;;` only | `;;` only | `//` only (does **not** accept `;;`) |

## Shared options (all three)

These options exist in all three implementations with compatible semantics. The
only difference is that CQLi accepts `--long` in addition to `-long`.

| Option | Args | Description |
|---|---|---|
| `-i` / `-input` | `file.pgn` | Input PGN file |
| `-o` / `-output` | `file.pgn` | Output PGN file |
| `-g` / `-gamenumber` | `N [M]` | Restrict to game number range |
| `-s` / `-singlethreaded` | — | Disable multi-threading |
| `-threads` | `N` | Set thread count |
| `-mainline` | — | Skip variations |
| `-variations` | — | Process variations |
| `-lineincrement` | `N` | Progress indicator frequency |
| `-matchstring` | `str` | Comment string for matches |
| `-noheader` | — | Suppress header comments |
| `-noremovecomment` | — | Ignore `removecomment` filters |
| `-nosettag` | — | Ignore `settag` filters |
| `-showmatches` | — | Print matching game numbers |
| `-silent` | — | Suppress all added comments |
| `-version` | — | Print version and exit |
| `-help` | — | Print help and exit |
| `-vi` | — | Shorthand for `-i HHdbVI.pgn` |
| `-cql` | `"filter"` | Inject filter text from CLI |
| `-fen` | `FEN` | Restrict to matching FEN |
| `-matchcount` | `N [M]` | Require N matching positions per game |
| `-assign` | `var val` | Assign variable on CLI |
| `-black` | `name` | Black player filter |
| `-white` | `name` | White player filter |
| `-player` | `name` | Either-colour player filter |
| `-event` | `name` | Event tag filter |
| `-site` | `name` | Site tag filter |
| `-result` | `str` | Result filter (`1-0`, `0-1`, `1/2-1/2`) |
| `-year` | `N [M]` | Year or year-range filter |
| `-flip` | — | Inject flip transform |
| `-flipcolor` | — | Inject flipcolor transform |
| `-reversecolor` | — | Inject reversecolor transform |
| `-shift` | — | Inject shift transform |
| `-rotate90` | — | Inject rotate90 transform |
| `-rotate45` | — | Inject rotate45 transform |
| `-fliphorizontal` | — | Inject fliphorizontal transform |
| `-flipvertical` | — | Inject flipvertical transform |
| `-shifthorizontal` | — | Inject shifthorizontal transform |
| `-shiftvertical` | — | Inject shiftvertical transform |
| `-virtualmainline` | — | Virtual mainline positions only |
| `-alwayscomment` | — | Disable smart comments |
| `-quiet` | — | Suppress match/auxiliary comments |

## CQLi-only options (not in CQL 6.1 or 6.2)

These exist only in CQLi. Passing them to CQL 6.x will cause an error.

### General

| Option | Args | Description |
|---|---|---|
| `--append` / `-a` | `file.pgn` | Append output instead of overwriting |
| `--createdirectories` | — | Create output directories as needed |
| `--dryrun` | — | Show output file names without creating them |
| `--limit` | `N` | Stop after N matching games |
| `--license` | — | Print license info and exit |
| `--maxopenoutputfiles` | `N` | Limit open output file handles |
| `--nestedcomments` | — | Allow nested `{...}` comments in input |
| `--noclobber` | — | Prevent overwriting existing output files |
| `--nosort` | — | Write matches immediately (skip sort, save memory) |
| `--skipunknownvariants` | — | Skip games with unrecognized Variant tags |
| `--variantalias` | `name alias` | Register alias for a chess variant name |
| `--vii` | — | Shorthand for `-i HHdbVII.pgn` |
| `-w` / `--warnlevel` | `1\|2\|3` | Diagnostic verbosity level |

### Feature options

| Option | Args | Description |
|---|---|---|
| `--keepallbest` | — | Keep multiple best-length matches for `line`/`sort`/`consecutivemoves` |
| `--noasyncmessages` | — | Queue messages until end of game |
| `--nocommitlog` | — | Disable enhanced smart comments (approximate CQL 6.1 behaviour) |
| `--noremovecomment` | — | Suppress `removecomment` side effects |
| `--noremovetag` | — | Suppress `removetag` side effects |
| `--nosmartcomments` | — | Alias for `--alwayscomment` |
| `--pipetimeout` | `N` | Command Pipe response timeout |
| `--secure` | — | Forbid `readfile`, `writefile`, `commandpipe` |
| `--showdictionaries` | — | Emit dictionary values after processing |

### PGN output formatting

| Option | Description |
|---|---|
| `--coalescecomments` / `--nocoalescecomments` | Merge multiple comments at one position into one |
| `--compactcomments` / `--nocompactcomments` | Space between braces and comment text |
| `--compactmoves` / `--nocompactmoves` | Space between move number and move |
| `--compactvariations` / `--nocompactvariations` | Space between parentheses and variation |
| `--elidecomments` / `--noelidecomments` | Strip all comments including originals |
| `--elidenags` / `--noelidenags` | Strip NAGs |
| `--elidevariations` / `--noelidevariations` | Strip variation lines |
| `--movenumberaftercomment` / `--nomovenumberaftercomment` | Force move numbers after comments |
| `--movenumberafternag` / `--nomovenumberafternag` | Force move numbers after NAGs |
| `--movenumbers` / `--nomovenumbers` | Emit/suppress move number indicators |
| `--splitmoves` / `--nosplitmoves` | Allow line break between move number and move |
| `--uniquecomments` / `--nouniquecomments` | Deduplicate comments at same position |
| `--pgnlinewidth` | `N` | Max PGN output line width (default 79) |

### Filter injection

| Option | Args | Description |
|---|---|---|
| `--btm` | — | Inject `btm` filter |
| `--wtm` | — | Inject `wtm` filter |
| `--hhdb` | varies | Inject HHdb filter |

### Debugging

| Option | Description |
|---|---|
| `--parse` | Dump parsed AST and exit (actually works, unlike CQL 6.x) |
| `--ansicolors` / `--noansicolors` | ANSI colour output with `--parse` |
| `--consoleunicode` / `--noconsoleunicode` | Unicode in error messages and `--parse` |

## CQL 6.2-only options (not in CQL 6.1 or CQLi)

These exist only in CQL 6.2. Passing them to CQL 6.1 or CQLi will cause an error.

| Option | Args | Description |
|---|---|---|
| `-a` | `file.cql` | Convert `.cql` file to ASCII (not the same as CQLi's `-a`/`--append`) |
| `-u` | `file.cql` | Convert `.cql` file from ASCII to Unicode |
| `-html` | `file.cql` | Generate HTML rendering of `.cql` file |
| `-similarposition` | `file.pgn` | Check positions against a reference PGN |

**Warning:** `-a` is overloaded — in CQL 6.2 it means "convert to ASCII", in CQLi
it means "append output". Never pass `-a` without knowing which binary is running.

## CQL 6.1-only options

CQL 6.1 has no options that are absent from both CQL 6.2 and CQLi. Every CQL 6.1
flag appears in at least one of the other two implementations.

## Default value differences

| Behaviour | CQL 6.1 | CQL 6.2 | CQLi 1.0.6 |
|---|---|---|---|
| Default match comment | `"CQL"` | `"CQL"` | `"CQL"` |
| Comment coalescing | Yes (merged) | Yes (merged) | **No** (separate `{A} {B}`); use `--coalescecomments` for CQL 6.x behaviour |
| Variable scoping | Visible outside iteration | Visible outside iteration | **Scoped** to iteration body; may break some CQL 6.x scripts |
| `--gui` / `--guipgnstdin` / `--guipgnstdout` | Supported | Supported | **Not supported** (planned for future) |
| `-parse` | Listed but "not supported" | Listed but "not supported" | **Functional** — dumps the AST |
| `-o stdout` | Not supported | Not supported | **Supported** — writes matching games to stdout |
| lineincrement default | 1000 | 1000 | 1000 (dot per 100 games, bracket per 1000) |
| Sorting | Always sorts | Always sorts | Sorts by default; `--nosort` available |

## Summary for `analyse_cql.py`

The script currently passes these flags to the CQL binary:

```
<binary> -i <pgn> -o <output> [-threads N] <script.cql>
```

All three implementations accept this invocation identically. The safe common
subset for `analyse_cql.py` to forward is:

- `-i`, `-o`, `-g`, `-threads`, `-s`, `-lineincrement`, `-mainline`, `-variations`
- `-matchstring`, `-silent`, `-quiet`, `-noheader`
- All filter-injection flags: `-black`, `-white`, `-player`, `-event`, `-site`,
  `-result`, `-year`, `-fen`, `-cql`, `-matchcount`, `-assign`
- All transform flags: `-flip`, `-flipcolor`, `-reversecolor`, `-shift`,
  `-rotate90`, `-rotate45`, `-fliphorizontal`, `-flipvertical`,
  `-shifthorizontal`, `-shiftvertical`

Flags that require runtime detection of the binary:

| Flag | Safe for |
|---|---|
| `--nosort` | CQLi only |
| `--limit` | CQLi only |
| `--append` / `-a` | CQLi only (**conflicts** with CQL 6.2's `-a`) |
| `-html`, `-u`, `-similarposition` | CQL 6.2 only |
| Any PGN output formatting flag | CQLi only |
