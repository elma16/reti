#!/usr/bin/env bash

fen_file="${1}"
png_dir="${2}"
tex_file="${3}"

# turn the fen file to a url compatible string
sed -i '' 's/ /%20/g' $fen_file

mkdir $png_dir

i=0
while IFS= read -r line; do
    i=$((i+1))
    name="$line"
    curl "https://fen2png.com/api/?fen=${name}&raw=true" > $png_dir/$i.png
done < "$fen_file"

#now for the tex bit

cat <<'EOF' >> $tex_file
\documentclass{article}
\usepackage{graphicx}

\date{}
\title{Elliott's Games!}

\begin{document}
\maketitle

\centering

Today's set of puzzles are mostly taken from the 2021 Online London Chess League, and a couple from the 2000 Bundesliga in Germany.
Once again, if you get stuck, ask one of the coaches to come and help! Write your solutions \textbf{in notation}.

EOF

# want to format it in pretty format.
# first page should have 4 puzzles, every subsequent page should have 6

count=1
for filepath in $png_dir/*.png; do
    filepath_noext="${filepath%.*}"
    if [ $count = 1 ] || [ $((count % 6)) = 5 ]
    then
        echo "\ begin{figure}[ht]" >> $tex_file
    fi
    if [ $((count % 6)) = 4 ]
    then
        echo "\ end{figure}" >> $tex_file
    fi
    echo "\ begin{minipage}[b]{0.5\linewidth}" >> $tex_file
    echo "\ centering" >> $tex_file
    echo "\includegraphics[width=7cm, height=7cm]{$filepath_noext}" >> $tex_file
    echo "\ caption*{How can I make this rubbish any better?}" >> $tex_file
    echo "\ vspace{4ex}" >> $tex_file
    echo "\ end{minipage}" >> $tex_file
    count=$((count+1))
done

cat <<'EOF' >> $tex_file

\end{document}

EOF
