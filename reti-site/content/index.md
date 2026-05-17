---
title: Reproducing the *Fundamental Chess Endings* Statistics Table using FOSS
date: 2026-05-16
author: Elliott Macneil
---

## Introduction

In Karsten Müller and Frank Lamprecht's classic work *Fundamental Chess Endings*, they give a table showing how often each ending from selected chapters occurs in practical games.[^fce] A simplified version of this table is available on Wikipedia.[^wikipedia] To produce the original table in 2001, Müller and Lamprecht used ChessBase and that year's Mega Database, containing about 1.7 million games. Later on in the book, they used analysis engines Fritz 6 and Nimzo 8, with five-piece tablebases for positions that were already solved. Much of that software stack was proprietary.

## Motivation

The chess software landscape looks very different in 2026. At time of writing, Stockfish 18 is the leading free and open-source chess engine,[^stockfish] and the majority of the top engines are also open source.[^ccrl] Large collections of games are also easier to obtain through aggregators such as Lumbra's Gigabase.[^lumbra] Five-piece tablebases are still useful, but complete seven-piece tablebases are now standard, though running one locally would require significant computational resources.

I wanted to see how far the original Müller-Lamprecht analysis could be reproduced and extended using FOSS tools.

For copyright reasons I am not reproducing the original table here in full. The public Wikipedia summary is linked for context, and this page focuses on my recomputed Gigabase statistics.

## Methodology

I downloaded roughly 17 million games from Lumbra's Gigabase: about 10 million over-the-board (OTB) games and about 7 million high-level online games. This is roughly an order of magnitude larger than the database used for the original table. The OTB and Online labels follow the Lumbra source buckets in the downloaded PGNs; I do not apply an additional rating filter in this page.

The next problem is locating and categorising the endings. This project uses Chess Query Language 6.1, originally developed by Costeff and Stiller,[^cql] further enhanced with Gamble's CQLi 1.0.6 implementation.[^cqli] The CQL scripts, preprocessing code, and static-site renderer are available in the accompanying GitHub repository.[^reti] CQL is a powerful language for filtering chess positions; the filters used here are deliberately simple queries. In this page, a marker is the comment inserted into an annotated PGN when CQL finds a position matching one of the FCE ending categories. A first-marker position is the first such position for a given game and ending.

I was also interested in how often tablebase evaluations line up with the final result of the game. For that reason, every qualifying first-marker position with five pieces or fewer is evaluated with local Syzygy WDL 3-4-5 tablebase files,[^syzygy] probed by Rust code using shakmaty and shakmaty-syzygy.[^shakmaty] Many FCE rows contain more than five pieces at the first marker, so the tablebase columns are intentionally blank when no five-piece-or-fewer first-marker positions qualify. Some example games are provided for context, and clicking on the position takes you to Lichess analysis, so you can analyse/play with an engine if you wish.[^lichess] 

## Table

The table below is interactive. Changing the corpus or minimum half-move setting updates the incidence counts, percentages, tablebase summaries, and sampled examples.

- **Games** counts qualifying ending incidences: one game can count once for each ending.
- **Corpus %** divides that row by all games in the selected corpus; **matched share %** divides it by all counted ending incidences.
- **TB WDL** uses Syzygy WDL for qualifying first-marker positions with five pieces or fewer.
- **Actual result** is scored from the named material side, not from White or Black.

## Results and Discussion

There are several interesting features. The broad agreement of my statistics with Müller and Lamprecht is very surprising. Some of these numbers might make sense because of relative "order" one ending flows into another (explored a bit later on in the transition section), but this seems to suggest a rough underlying distribution to high-level chess games.

My first hypothesis is that this distribution might not hold if broad rating categories are considered. Perhaps it might be more random? My second hypothesis is that the choice of opening somewhat influences the distribution of the ending. Depending on which ending is chosen, certain pieces are more likely to be exchanged, which increases the likelihood of a complementary ending occurring. These are just thoughts, and I've not explored them much since.

Considering the table again, some statistics are interesting. For example, the row "8.2a Rook + Bishop vs Rook without pawns" can show a higher practical win rate than the tablebase result alone would suggest, which is plausible because this ending is easy for humans to mishandle. What I was not expecting is how huge the gap between tablebase and reality is! On the other hand, I was also surprised by the practical win rate for king, bishop and knight versus king: it is theoretically won, but still non-trivial to execute over the board. Switching the corpus from OTB (generally longer time controls) to online (generally shorter time controls), we see a drop in conversion rate, which is expected.

## Transitions

An extension to the original analysis is counting consecutive first-marker transitions between endings, rather than estimating literal transition probabilities. For each game, the qualifying endings are ordered by the first ply at which their qualifying run appears; the Sankey diagram counts adjacent pairs in that sequence. This makes it a descriptive view of observed co-occurrence and order, not a causal model.

## Conclusion

The fact that this project was possible at all makes me happy. In the process of writing this down, further ideas emerged. I would be happy to hear any of yours if this was of interest to you. 

## References

[^fce]: Karsten Müller and Frank Lamprecht. [*Fundamental Chess Endings*](https://books.google.co.uk/books/about/Fundamental_Chess_Endings.html?id=HfwEAAAACAAJ&redir_esc=y). Gambit, 2001.
[^wikipedia]: Wikipedia. ["Chess endgame", frequency table](https://en.wikipedia.org/wiki/Chess_endgame#Frequency_table).
[^stockfish]: The Stockfish team. [Stockfish 18](https://stockfishchess.org/blog/2026/stockfish-18/). Free and open-source chess engine release page.
[^ccrl]: Computer Chess Rating Lists. [CCRL 40/15 rating list, all engines](https://computerchess.org.uk/4040/rating_list_all.html). Used as a contemporary engine-strength reference.
[^lumbra]: Lumbra's Gigabase. [Free chess game database for Scid and PGN](https://lumbrasgigabase.com/en/). PGN export used as the game corpus.
[^cql]: Gady Costeff and Lewis Stiller. [Chess Query Language 6.1 documentation](https://www.gadycosteff.com/cql-6-1/).
[^cqli]: Robert Gamble. [CQLi](https://cql64.com/). Version 1.0.6 used for the combined marker run.
[^reti]: Elliott Macneil. [Reti project source repository](https://github.com/elma16/reti). CQL scripts, Rust preprocessing code, and static-site renderer.
[^syzygy]: Ronald de Man. [Syzygy endgame tablebases](https://www.chessprogramming.org/Syzygy_Bases). Local 3-4-5-piece WDL files used for tablebase outcomes.
[^shakmaty]: Niklas Fiekas. [shakmaty](https://github.com/niklasf/shakmaty) 0.28 and [shakmaty-syzygy](https://github.com/niklasf/shakmaty-syzygy) 0.26. Rust crates used for move replay, FEN handling, and Syzygy probing.
[^lichess]: Lichess. [Analysis board](https://lichess.org/analysis) and [open-source project information](https://lichess.org/source). Used for outbound position-analysis links.
