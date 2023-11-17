/************
Find pairs of positions in win studies
differing only in that the source is missing at least one white
piece compared to the target
This was the study theme of the 7th World Chess Composition Tournament
***********/

cql(input hhdbvi.pgn result 1-0)
  echo (source target){
    source≺target
    sidetomove==source:sidetomove
    mismatches= ~(source∩target)
    mismatches
    mismatches== □ ∩ source:△   ///"missing: " mismatches
   }

