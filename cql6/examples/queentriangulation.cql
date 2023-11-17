/*Queen triangulation:
 The winning side loses a tempo using only queen moves,
 forcing the losing side to move a pawn.
*/

cql(input hhdbvi.pgn sort matchcount 2 1000 quiet)
⬓{
 result 1-0
 source=∙
 wtm
 ⊢ nestban
    (♕―― ――)+
     ♕―― source∩∙==▦
     ♟―― ///"thematic pawn move"
}