/* Queen sac, followed by double check, followed by mate.

Reminicent of the game reti - tartakower vienna 1910
*/

cql()

flipcolor {
line quiet 
  --> move from Q to [a_] 
  --> move from a to Q
  --> move from A to [Aa_]
  --> A attacks k == 2
  --> move from A to [Aa_]
  --> mate} 
