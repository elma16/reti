# reti
A collection of cql scripts for endgame studies in pgn files.

## Introduction

In Müller and Lamprecht's celebrated work "Fundamental Chess Endgames", [they show a table on page 11 (this is from the Amazon website free sample of the book)](https://www.amazon.co.uk/Fundamental-Chess-Endings-One-Encyclopaedia/dp/1901983536?asin=B00BJ64LMW&revisionId=e8148266&format=1&depth=1). In it, they mention the use of Mega Database 2001, a proprietary database by Chessbase. Obtaining a copy of this to reproduce their table would be ~£100. It's now 2022, and open source chess has come a long way, and now it is trivial to obtain databases 100 times larger than this, completely for free. Namely, Lichess has an [open source database of games played on their website](https://database.lichess.org/#standard_games). The final piece of the puzzle is finding a way to obtain the required values. For this I used Gady Costeff's [CQL : Chess Query Language](http://www.gadycosteff.com/cql/). The result is a collection of scripts which can be run to analyse how often an ending occurs.

## But wait, there's more!

This analysis is not limited to just some big database, this can be done on _any_ pgn file you have available to you!

## Installation

To install, simply clone the repository

``` shell
gh repo clone elma16/reti
```

you will also need cql.

## Usage 

``` shell
source FCE-table.sh path/to/cql/executable path/to/database.pgn path/to/output/folder
```
