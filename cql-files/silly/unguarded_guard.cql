// Unguarded Guard (CQL6)
// Interposing on an unguarded square to block a line-check.
// Looks for a checking line-piece (rook/queen on rank/file, bishop/queen on diagonal),
// and a legal interposition onto an empty, undefended square that stops the check.

cql(
  input "path/to/games.pgn"
  output "output/unguarded-guard.pgn"
  quiet
)

flipcolor

find {
  Block[element]{
    parent:check
    parent:piece Checker=[rbq] parent:Checker->Block->k
    parent:Block==.
    parent:not A->Block
    move to Block
    not check
    sort "unguarded guard ply" ply
    comment("Unguarded guard: interposed on " Block)
  }
}
