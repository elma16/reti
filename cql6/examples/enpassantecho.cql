/*******
Two positions differ only in whether en passant is legal
**********/

cql(input hhdbvi.pgn variations )
   move enpassant
   echo (source target){
     sidetomove==source:sidetomove
     not move legal enpassant
     source&target==.
     }
     
     
