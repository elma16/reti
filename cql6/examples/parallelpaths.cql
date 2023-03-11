/*Find games in which two distinct pieces P1 and P2
  of the same type each traverse at some point the same k squares in the
  same order, for k at least 3. Each piece's traversal of these squares
  must occur without any intervening squares visited by the piece.
*/

cql(input hhdbvi.pgn quiet)
function parallel(Pos1 piece1 Pos2 piece2){
 current1=Pos1 current2=Pos2
 seensofar=~.
 loop{
  current1=current1:find move from piece1
  current2=current2:find move from piece2
  Dest=?current1:move to . 
  Dest==current2:move to .
  not Dest in seensofar //make sure Dest is new
  seensofar=seensofar|Dest
  current1=current1:child current2=current2:child
  current1:comment("First mover " #seensofar)
  current2:comment("Second mover " #seensofar)
  }
 #seensofar
}
piece FirstMover=move from [RrNnBbQq]
echo(source target) {
  source<target
  piece SecondMover=move from [RrNnBbQq] & ~FirstMover
  type SecondMover==source:type FirstMover
  sort "Max length of run"
      parallel (source FirstMover target SecondMover)
           >=3
}
