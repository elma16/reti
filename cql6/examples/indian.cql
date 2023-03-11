/*Indian theme:
 White moves a line piece over a critical square
 Then white moves another piece to the critical square without checking, preventing
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
 kingfield= .attackedby k
 square all x in kingfield{
   a & x
   or A attacks x
   or xray (rear critical x)
 }
 not xray(rear critical k)
 square all x in a & ~k{
   not move legal from x
   or
   xray (rear critical x k)
   }
 {square x in [_A]&kingfield
    xray (rear critical x)}
 or
  square x in a
    xray (rear critical x k)
}

piece criticalpiece=move from [RBQ]
dest=move to .
square criticalsquare in between(criticalpiece dest)
 piece interferer in [RBNP]&~criticalpiece
  line-->move from criticalpiece to dest comment ("CQL critical move by " criticalpiece " over " criticalsquare)
      -->not move from criticalpiece*
      -->move from interferer to criticalsquare comment ("interfering move to " criticalsquare)
      -->virtualstalemate(criticalpiece criticalsquare) 
      -->not move from (interferer | criticalpiece)*
      -->move from interferer comment ("interferer moves away")
      -->criticalpiece attacks criticalsquare
      
