#!/usr/bin/env bash

cql_dir="${1}"
db_dir="${2}"
output_dir="${3}"
match_count="${4}"

"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/1-4BN.pgn -matchcount "${match_count}" src/1-4BN.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/2-0Pp.pgn -matchcount "${match_count}" src/2-0Pp.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/2-1KPk.pgn -matchcount "${match_count}" src/2-1KPk.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/3-1Np.pgn -matchcount "${match_count}" src/3-1Np.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/3-2NN.pgn -matchcount "${match_count}" src/3-2NN.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/4-1Bp.pgn -matchcount "${match_count}" src/4-1Bp.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/4-2scBB.pgn -matchcount "${match_count}" src/4-2scBB.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/4-3ocBB.pgn -matchcount "${match_count}" src/4-3ocBB.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/5-0BvsN.pgn -matchcount "${match_count}" src/5-0BvsN.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/6-1-0Rp.pgn -matchcount "${match_count}" src/6-1-0RP.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/6-2-1RPr.pgn -matchcount "${match_count}" src/6-2-1RPr.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/6-2-2RPPr.pgn -matchcount "${match_count}" src/6-2-2RPPr.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/6-2Rr.pgn -matchcount "${match_count}" src/6-2Rr.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/6-3RRrr.pgn -matchcount "${match_count}" src/6-3RRrr.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/7-1RN.pgn -matchcount "${match_count}" src/7-1RN.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/7-2RB.pgn -matchcount "${match_count}" src/7-2RB.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/8-1RNr.pgn -matchcount "${match_count}" src/8-1RNr.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/8-2RBr.pgn -matchcount "${match_count}" src/8-2RBr.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/8-3RAra.pgn -matchcount "${match_count}" src/8-3RAra.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/9-1Qp.pgn -matchcount "${match_count}" src/9-1Qp.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/9-2Qq.pgn -matchcount "${match_count}" src/9-2Qq.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/9-3QPq.pgn -matchcount "${match_count}" src/9-3QPq.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/10-1Qa.pgn -matchcount "${match_count}" src/10-1Qa.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/10-2Qr.pgn -matchcount "${match_count}" src/10-2Qr.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/10-3Qaa.pgn -matchcount "${match_count}" src/10-3Qaa.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/10-4Qra.pgn -matchcount "${match_count}" src/10-4Qra.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/10-5Qrr.pgn -matchcount "${match_count}" src/10-5Qrr.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/10-6Qaaa.pgn -matchcount "${match_count}" src/10-6Qaaa.cql
"${cql_dir}" -i "${db_dir}" -o "${output_dir}"/10-7QAq.pgn -matchcount "${match_count}" src/10-7QAq.cql
