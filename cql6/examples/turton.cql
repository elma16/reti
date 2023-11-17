/*************
This example code finds Turtons (including Lloyd-Turton and
Brunner-Turton) in the mainline.

At the start of the Turton, there are two line pieces (i.e. Q, R or
B).  Each attacks a key square, called the critical square, C.

We call these two line pieces T and U.

The idea of the Turton is that instead of U initially moving to the
critical square, first piece T crosses the critical square. Only after
T's crossing does U move to the critical square (from a different
direction).

By doing so, the T and U form a battery, one that has the exact
opposite orientation to the battery that would be formed had T moved
first, before U crossed C

***************/
cql (input hhdbvi.pgn quiet)
 ◭T∊♕♖♗ ◭U∊♕♖♗∩~T C∊□←U
   ⊢◎T∪U 
    T――□ T→C→from   ///"T crosses critical square " C
    U――C            ///"U to critical square"
    U―― T→C→U       ///"U moves supported by T"

