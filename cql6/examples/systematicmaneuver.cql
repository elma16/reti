/*Systematic maneuvers:
 1. At a position X,
 2. there is a set M of at least 4 pieces in X
 3. a pair (r, f) of rank/file offsets, not both 0,
 4. a positive ply increment inc 
 5. a number of repetitions k>=3 such that

 for each i between 1 and k, the position X' that is i*inc plies
 later than X has these properties:
    A. The position of each piece in M in X has been shifted
    by i*r rank and i*f file to get its position in X', and
    B. Each piece not in M in X either does not exist in X' or
       is on the same square in X as in M'
*/       

cql (input hhdbvi.pgn quiet)
function checkmaneuver(inc){
 start=∙
 firstmaneuver=position positionid+inc
  movers=
       ◭x∊◭{
         firstmaneuver:x
         x≠firstmaneuver:x}
 movers≥4 //change this line to get different numbers of movers
 seen=0
 ∀◭x∊movers
   if seen==0{
     deltarank=firstmaneuver:rank x - rank x
     deltafile=firstmaneuver:file x - file x
     seen=1}
   else{
     deltarank==firstmaneuver:rank x - rank x
     deltafile==firstmaneuver:file x - file x
   }
 find 3 100 {
    (positionid - start:positionid)%inc==0
    maneuvernumber=(positionid-start:positionid)/inc
    ∀◭x∊◭{
      if start:x in movers
           {rank x - start:rank x == maneuvernumber * deltarank
	    file x -start:file x == maneuvernumber * deltafile}
      else
          x==start:x}
    if maneuvernumber>0
     ///"Maneuver repeat: " maneuvernumber " starting from: " start
   }//find all
 sort "number of participants" movers
 ///"CQL maneuver found with movers: " movers " and ply increment: " inc
}//checkmaneuver

currinc=2
success=0
loop{
 if checkmaneuver(currinc) success=1
 currinc+=2
 currinc≤20}
success==1

