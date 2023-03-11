/*********
look for rook visiting the four corners
**********/

cql( input hhdbvi.pgn )
initial
 piece Candidate in R{
  find Candidate==a1
  find Candidate==a8
  find Candidate==h1
  find Candidate==h8
}