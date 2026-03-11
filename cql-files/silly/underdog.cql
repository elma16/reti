/* #290: losses in (queen) and pawn endings where the side with less pawns wins */
cql()

flipcolor {result 1-0 
power A < power a}
[QqRrBbNn] == 0