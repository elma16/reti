/**********
Find games where one side wins,
but is down at least a queen's worth of material
for at least 5 consecutive moves,
sorted by the length of time he was down the material
**********/

cql(input hhdbvi.pgn)

flipcolor
 {result 1-0
  sort "Number of consecutive ply winner is down at least 9"
     line 5 1000 nestban
       -->power a - power A >= 9 +
 }
		       

