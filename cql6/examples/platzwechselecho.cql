cql(input hhdbvi.pgn)
◭N1∊♘ ◭N2∊♞{
     abs (rank N1 - rank N2)≥3 
     abs (file N1 - file N2)≥3
     echo (s t){
       s≺t
       N1==s:N2
       N2==s:N1
       ///"Platzwechsel: " N1 " and " N2 " switched places"
    }
}    
