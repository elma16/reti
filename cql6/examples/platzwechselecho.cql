cql(input hhdbvi.pgn)
piece N1 in N
 piece N2 in n{
     abs (rank N1 - rank N2) >=3 
     abs (file N1 - file N2) >=3
     echo (s t){
       s<t
       N1==s:N2
       N2==s:N1
       comment("Platzwechsel: " N1 " and " N2 " switched places")
    }
}    
