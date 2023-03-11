/*********
Find games with quadrupled pawns. This uses
the square filter
**********/

cql(input hhdbvi.pgn)
 square s in a-h1
  flipcolor
    P&vertical s
      >=4


