/*******
Two positions differ only in whether en passant is legal
**********/

cql(input hhdbvi.pgn variations )
   ――(enpassant)
   echo (source target){
     sidetomove==source:sidetomove
     source∩target==▦
     not legal ――(enpassant)
     }
     
     
