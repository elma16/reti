/********
Platzwechseln theme.
A white and black knight switch places.
They are separated by at least 3 squares both horizontally and vertically
*********/

cql(input hhdbvi.pgn )
Start=∙
◭N1∊♘ ◭N2∊♞ {
   abs (rank N1 - rank N2) ≥3 
   abs (file N1 - file N2) ≥3
   find N1 == Start:N2
        and  N2 == Start:N1
   } 















