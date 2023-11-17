/*Indian theme:
 White moves a line piece C over a critical square S
 Then white moves another piece I to the critical square without checking, preventing
 what would be a stalemate without the interference
 Later white moves the interfering piece away
*/

cql(input hhdbvi.pgn quiet result 1-0)
/* A "virtual stalemate" is not a stalemate,
but would be one if the piece on the argument
'critical' did not block the line piece on the
square 'rear'
*/

function virtualstalemate(rear critical){
 btm
 not check
 not stalemate
 kingfield= ▦←♚
 ∀x∊kingfield{
   ▲ ∩ x
   or △→x
   or rear→critical→x
 }
 not rear→critical→♚
 ∀x∊▲ ∩ ~♚{
   not legal x――
   or
   rear→critical→x→♚
   }
 {x∊□△∩kingfield
    rear→critical→x}
 or
  x∊▲
    rear→critical→x→♚
}
/* C is the critical piece, that traverses
   S,   the critical square.
   I is the interfering piece, which
         moves to S, blocking C and preventing stalemate
*/

◭C = ♖♗♕――(from)
S ∊ □←C
 ◭I ∊ ♖♗♘♙∩~C
  ⊢◎ I∪C
   C―― C→S→from ///"critical move over " S
   I――*
   I――S ///"interfering move to " S
      virtualstalemate(C S)
   I――  ///"interferer moves away"
      C→S
      
