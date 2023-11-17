/* 
Find games in which there is a "two-piece cycle" in which two pieces,
   T1 (a black piece) and T2 (a white piece), each traverse
   the same set of squares. T1 starts, then T2 moves to a
   square, then T1 moves to a new square, and so on, until each
   piece's final move ends on the same square as that piece's initial
   square.  Thus, the path of each piece forms a cycle. The moves need not
   be consecutive (unlike in the CQL 6.1 version).  
   Games are sorted by length of cycle.
*/   

cql (input hhdbvi.pgn)

◭T1∊▲
 ◭T2∊△ {
   C1 = T1 //cycle traversed by T1
   C2 = T2 //cycle traversed by T2
   Start=∙
   sort "cycle length"
    ⊢◎T1∪T2 piecepath
        (T1――~C1 C1=C1∪T1
         T2――~C2 C2=C2∪T2)+
	 T1――Start:T1
	 T2――Start:T2
              C1==C2
}

 