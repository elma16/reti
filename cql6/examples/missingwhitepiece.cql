/*Find There are two positions source and target in a win study.
  source is in the mainline, target in a try. 
  source differs from target only in that
  target has some extra white pieces
*/

cql(input hhdbvi.pgn result 1-0 variations matchstring "")
  mainline
  sort "number of identical consecutive moves"
   echo (source target){
    try
    sidetomove==source:sidetomove
    mismatches= ~(source∩target)
    mismatches>0
    mismatches== △ ∩ source:□
    ///"extra pieces: " mismatches
    source:///"missing pieces: " mismatches
    consecutivemoves 15 100 (source target)
   }

