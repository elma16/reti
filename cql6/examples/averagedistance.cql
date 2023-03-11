/* Find games with maximum average move length in the main line.
   All distances are scaled by a factor of 1000.
   Only studies with more than 10 ply and with average distance>4 are included
*/

cql(input hhdbvi.pgn quiet)
Scale=1000
function scaledD(x y){
 drank = Scale* (rank x - rank y)
 dfile = Scale* (file x - file y)
 sqrt(drank*drank + dfile*dfile)
}
initial
Sum=0
find all
 Sum+=scaledD(move from . move to .)
find {terminal
      ply>10
      sort "Average move length"
        Sum/ply>4*Scale}
