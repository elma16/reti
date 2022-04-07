#!/usr/bin/env bash

# given a directory with pgn files, output
# 1) an output directory with pgn breakdown by fundamental ending
# 2) spreadsheet of statistics comparing it with megadatabase 2001

cql_dir="${1}"
db_dir="${2}"
output_dir="${3}"

rm -rf "${output_dir}"
mkdir -p "${output_dir}"
rm -rf examples
mkdir examples

for pgnpath in "${db_dir}"/*.pgn; do
    total_games=$(grep -o 'Result' "$pgnpath" | wc -l)
    pgnname=$(basename -- "$pgnpath")
    pgnname_noext="${pgnname%.*}"
    mkdir -p  "${output_dir}"/"$pgnname_noext"

    for filepath in src/FCE/*.cql; do
        filename=$(basename -- "$filepath")
        filename_noext="${filename%.*}"
        "${cql_dir}" -i "$pgnpath" -o "${output_dir}"/"$pgnname_noext"/"$filename_noext".pgn \
            -matchcount 2 100  "$filepath"
        grep -o 'Result' "${output_dir}"/"$pgnname_noext"/"$filename_noext".pgn |
            wc -l >> "${output_dir}"/"$pgnname_noext"/number_of_games.csv
    done

# calculate statistics
awk -v c=${total_games} '{for (i = 1; i <= NF; ++i) $i /= (c / 100); print }' OFS='\t' \
    ${output_dir}/"$pgnname_noext"/number_of_games.csv > ${output_dir}/"$pgnname_noext"/stats1.csv

#add pgn name to top of file
cat <(echo "$pgnname_noext") "${output_dir}"/"$pgnname_noext"/stats1.csv >>  "${output_dir}"/"$pgnname_noext"/stats.csv
echo "$total_games" >> "${output_dir}"/"$pgnname_noext"/stats.csv
done

# concatenate csv files vertically
i=1
for stat_file in $(find . -name 'stats.csv'); do
    i=$((i+1))
    cp ${stat_file} examples/stats_"$i".csv
done

paste -d, examples/*.csv > examples/total.csv
