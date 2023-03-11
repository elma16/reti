/*Find There are two positions source and target in a win study.
  source is in the mainline. It differs from target only in that
  target has some extra white pieces
*/

cql(input hhdbvi.pgn result 1-0 variations matchstring "")
  mainline
  sort "number of identical consecutive moves"
   echo (source target){
    variation
    sidetomove==source:sidetomove
    mismatches= ~(source&target)
    mismatches>0
    mismatches== A & source:_
    comment("extra pieces: " mismatches)
    source:comment("missing pieces: " mismatches)
    consecutivemoves 15 100 (source target)
   }

