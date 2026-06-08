// 290: losses in (queen) and pawn endings where the side with less pawns wins
// want to avoid positions where it's temporary (like a pawn capture in a pawn ending)

cql()

line <-- ({
    flipcolor {result 1-0 power A < power a}
    [QqRrBbNn] == 0
}) {3,}

