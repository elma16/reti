/***********
The Fata Morgana theme : btm position occurs 
at least 10 ply later than the original wtm position,
sorted by the length of the difference
**********/

cql(input hhdbvi.pgn result 1-0)
wtm
sort "Fata Morgana theme length"
 echo (source target){
   btm
   source∩target==▦
   ply-source:ply≥10
 }



 
 
