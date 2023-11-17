/*********
This the platzwechseln theme: two (white) knights interchange places
*********/

cql( input hhdbvi.pgn )
 Start=∙
 ◭N1∊♘ ◭N2∊♘∩~N1
   find N1 == Start:N2
        and  N2 == Start:N1
         
