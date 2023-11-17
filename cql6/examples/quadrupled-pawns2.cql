/*********
Find games with quadrupled pawns. This uses
the square filter
**********/

cql(input hhdbvi.pgn)
 s∊a-h1
  ⬓
    ♙∩vertical s
      ≥4


