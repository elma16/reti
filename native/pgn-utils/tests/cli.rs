//! End-to-end tests that drive the binary as the Python wrapper does.
//!
//! Two goals:
//!  1. *Regression*: lock in the legacy `INPUT OUTPUT` / `--inspect` /
//!     `--preserve-markup` invocations and the JSON stats they print, so we
//!     can extend the CLI without breaking `src/reti/pgn_utils.py`.
//!  2. *New surface*: smoke-test each new subcommand (`clean`, `concat`,
//!     `dedup`, `lint`).
//!
//! These tests use `env!("CARGO_BIN_EXE_reti-pgn-utils")` so no extra
//! testing crate (assert_cmd / etc.) is needed.

use std::fs;
use std::path::PathBuf;
use std::process::{Command, Stdio};

fn binary_path() -> PathBuf {
    PathBuf::from(env!("CARGO_BIN_EXE_reti-pgn-utils"))
}

fn tmpdir(label: &str) -> PathBuf {
    let mut dir = std::env::temp_dir();
    dir.push(format!("reti-pgn-test-{}-{}", label, std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

fn run(args: &[&str]) -> (String, String, i32) {
    let output = Command::new(binary_path())
        .args(args)
        .env("CLICOLOR", "0")
        .stdin(Stdio::null())
        .output()
        .expect("failed to spawn binary");
    let stdout = String::from_utf8_lossy(&output.stdout).into_owned();
    let stderr = String::from_utf8_lossy(&output.stderr).into_owned();
    let code = output.status.code().unwrap_or(-1);
    (stdout, stderr, code)
}

fn json_field(json: &str, key: &str) -> Option<String> {
    // Tiny extractor good enough for our flat JSON stats.
    let needle = format!("\"{key}\":");
    let start = json.find(&needle)? + needle.len();
    let tail = &json[start..];
    let end = tail
        .find(|c: char| c == ',' || c == '}' || c == ']')
        .unwrap_or(tail.len());
    Some(tail[..end].trim().trim_matches('"').to_string())
}

// ---- legacy form ---- //

#[test]
fn legacy_clean_strips_markup_and_emits_json_stats() {
    let dir = tmpdir("legacy-clean");
    let input = dir.join("in.pgn");
    let output = dir.join("out.pgn");
    fs::write(
        &input,
        b"[Event \"x\"]\n[Result \"1-0\"]\n\n1. e4 {comment} (1. d4) e5 1-0\n",
    )
    .unwrap();

    let (stdout, stderr, code) = run(&[
        "--no-progress",
        input.to_str().unwrap(),
        output.to_str().unwrap(),
    ]);
    assert_eq!(code, 0, "stderr: {stderr}");

    let written = fs::read_to_string(&output).unwrap();
    assert!(!written.contains('{'), "comment should be stripped");
    assert!(!written.contains('('), "variation should be stripped");
    assert_eq!(
        json_field(&stdout, "comments_removed").as_deref(),
        Some("1")
    );
    assert_eq!(
        json_field(&stdout, "variations_removed").as_deref(),
        Some("1")
    );
    assert_eq!(json_field(&stdout, "games_written").as_deref(), Some("1"));
    assert_eq!(json_field(&stdout, "removed_bom").as_deref(), Some("false"));
}

#[test]
fn legacy_inspect_writes_no_file_but_reports_stats() {
    let dir = tmpdir("legacy-inspect");
    let input = dir.join("in.pgn");
    fs::write(
        &input,
        b"[Event \"x\"]\n[Result \"*\"]\n\n1. e4 {comment} *\n",
    )
    .unwrap();

    let (stdout, stderr, code) = run(&["--no-progress", "--inspect", input.to_str().unwrap()]);
    assert_eq!(code, 0, "stderr: {stderr}");
    assert_eq!(
        json_field(&stdout, "comments_removed").as_deref(),
        Some("1")
    );
    assert!(stdout.contains("\"games_written\":1"));
}

#[test]
fn legacy_preserve_markup_keeps_braces_and_parens() {
    let dir = tmpdir("legacy-preserve");
    let input = dir.join("in.pgn");
    let output = dir.join("out.pgn");
    fs::write(
        &input,
        b"[Event \"x\"]\n[Result \"1-0\"]\n\n1. e4 {keep me} (1. d4) e5 1-0\n",
    )
    .unwrap();

    let (_stdout, stderr, code) = run(&[
        "--preserve-markup",
        "--no-progress",
        input.to_str().unwrap(),
        output.to_str().unwrap(),
    ]);
    assert_eq!(code, 0, "stderr: {stderr}");
    let written = fs::read_to_string(&output).unwrap();
    assert!(written.contains("{keep me}"));
    assert!(written.contains("(1. d4)"));
}

#[test]
fn legacy_json_field_order_unchanged() {
    // The Python wrapper currently doesn't depend on the order, but locking
    // the order down protects against accidental rearrangements in
    // `CleanStats::to_json`.
    let dir = tmpdir("legacy-fields");
    let input = dir.join("in.pgn");
    let output = dir.join("out.pgn");
    fs::write(&input, b"[Event \"x\"]\n[Result \"*\"]\n\n1. e4 *\n").unwrap();

    let (stdout, _stderr, code) = run(&[
        "--no-progress",
        input.to_str().unwrap(),
        output.to_str().unwrap(),
    ]);
    assert_eq!(code, 0);
    let expected_order = [
        "removed_bom",
        "invalid_utf8_replaced",
        "control_characters_removed",
        "games_written",
        "comments_removed",
        "variations_removed",
        "line_comments_removed",
    ];
    let mut last_pos = 0usize;
    for key in expected_order {
        let needle = format!("\"{key}\":");
        let pos = stdout.find(&needle).expect(&format!("missing {key}"));
        assert!(pos >= last_pos, "{key} appeared out of order");
        last_pos = pos;
    }
}

// ---- new subcommands ---- //

#[test]
fn clean_subcommand_matches_legacy_output() {
    let dir = tmpdir("sub-clean");
    let input = dir.join("in.pgn");
    let legacy_out = dir.join("legacy.pgn");
    let sub_out = dir.join("sub.pgn");
    fs::write(
        &input,
        b"[Event \"x\"]\n[Result \"1-0\"]\n\n1. e4 {c} (1. d4) e5 1-0\n",
    )
    .unwrap();

    let (_, _, c1) = run(&[
        "--no-progress",
        input.to_str().unwrap(),
        legacy_out.to_str().unwrap(),
    ]);
    let (_, _, c2) = run(&[
        "clean",
        "--no-progress",
        input.to_str().unwrap(),
        sub_out.to_str().unwrap(),
    ]);
    assert_eq!(c1, 0);
    assert_eq!(c2, 0);
    assert_eq!(
        fs::read(&legacy_out).unwrap(),
        fs::read(&sub_out).unwrap(),
        "subcommand output should be byte-identical to legacy"
    );
}

#[test]
fn concat_combines_two_files() {
    let dir = tmpdir("concat");
    let a = dir.join("a.pgn");
    let b = dir.join("b.pgn");
    let out = dir.join("out.pgn");
    fs::write(&a, b"[Event \"a\"]\n[Result \"1-0\"]\n\n1. e4 1-0\n").unwrap();
    fs::write(&b, b"[Event \"b\"]\n[Result \"0-1\"]\n\n1. d4 0-1\n").unwrap();

    let (stdout, stderr, code) = run(&[
        "concat",
        "--no-progress",
        "-o",
        out.to_str().unwrap(),
        a.to_str().unwrap(),
        b.to_str().unwrap(),
    ]);
    assert_eq!(code, 0, "stderr: {stderr}");

    let written = fs::read_to_string(&out).unwrap();
    assert!(written.contains("[Event \"a\"]"));
    assert!(written.contains("[Event \"b\"]"));
    // Ensure exactly one blank line separates them (no triple newline).
    assert!(!written.contains("\n\n\n"));
    assert_eq!(json_field(&stdout, "files_processed").as_deref(), Some("2"));
}

#[test]
fn concat_walks_directories() {
    let dir = tmpdir("concat-dir");
    let pgn_dir = dir.join("games");
    fs::create_dir_all(&pgn_dir).unwrap();
    fs::write(
        pgn_dir.join("01.pgn"),
        b"[Event \"a\"]\n[Result \"1-0\"]\n\n1. e4 1-0\n",
    )
    .unwrap();
    fs::write(
        pgn_dir.join("02.pgn"),
        b"[Event \"b\"]\n[Result \"0-1\"]\n\n1. d4 0-1\n",
    )
    .unwrap();
    fs::write(pgn_dir.join("README.md"), b"ignored").unwrap();

    let out = dir.join("out.pgn");
    let (stdout, _, code) = run(&[
        "concat",
        "--no-progress",
        "-o",
        out.to_str().unwrap(),
        pgn_dir.to_str().unwrap(),
    ]);
    assert_eq!(code, 0);
    assert_eq!(json_field(&stdout, "files_processed").as_deref(), Some("2"));
    let written = fs::read_to_string(&out).unwrap();
    assert!(written.contains("[Event \"a\"]"));
    assert!(written.contains("[Event \"b\"]"));
}

#[test]
fn concat_with_dedup_drops_duplicate_games_across_files() {
    let dir = tmpdir("concat-dedup");
    let a = dir.join("a.pgn");
    let b = dir.join("b.pgn");
    let out = dir.join("out.pgn");
    fs::write(&a, b"[Event \"a\"]\n[Result \"1-0\"]\n\n1. e4 e5 1-0\n").unwrap();
    fs::write(&b, b"[Event \"b\"]\n[Result \"1-0\"]\n\n1. e4 e5 1-0\n").unwrap();

    let (stdout, _, code) = run(&[
        "concat",
        "--no-progress",
        "--dedup",
        "-o",
        out.to_str().unwrap(),
        a.to_str().unwrap(),
        b.to_str().unwrap(),
    ]);
    assert_eq!(code, 0);
    assert_eq!(
        json_field(&stdout, "duplicates_removed").as_deref(),
        Some("1")
    );
    assert_eq!(json_field(&stdout, "games_written").as_deref(), Some("1"));
}

#[test]
fn dedup_keeps_first_occurrence() {
    let dir = tmpdir("dedup");
    let input = dir.join("in.pgn");
    let output = dir.join("out.pgn");
    fs::write(
        &input,
        b"[Event \"a\"]\n[White \"X\"]\n[Result \"1-0\"]\n\n1. e4 e5 1-0\n\n[Event \"b\"]\n[White \"Y\"]\n[Result \"1-0\"]\n\n1. e4 e5 1-0\n",
    )
    .unwrap();
    let (stdout, _, code) = run(&[
        "dedup",
        "--no-progress",
        "-o",
        output.to_str().unwrap(),
        input.to_str().unwrap(),
    ]);
    assert_eq!(code, 0);
    assert_eq!(json_field(&stdout, "games_written").as_deref(), Some("1"));
    let written = fs::read_to_string(&output).unwrap();
    assert!(written.contains("[White \"X\"]"));
    assert!(!written.contains("[White \"Y\"]"));
}

#[test]
fn lint_reports_issues_and_exits_nonzero() {
    let dir = tmpdir("lint-issues");
    let input = dir.join("in.pgn");
    fs::write(
        &input,
        b"[Event \"x\"]\n[Site \"x\"]\n[Date \"24-01-01\"]\n[Round \"1\"]\n[White \"a\"]\n[Black \"b\"]\n[Result \"1-0\"]\n\n1. e4 e5 0-1\n",
    )
    .unwrap();
    let (stdout, _stderr, code) = run(&["lint", "--no-progress", input.to_str().unwrap()]);
    assert_eq!(code, 2, "lint should exit 2 when issues present");
    assert!(stdout.contains("bad-date"), "stdout: {stdout}");
    assert!(stdout.contains("result-mismatch"), "stdout: {stdout}");
}

#[test]
fn lint_clean_input_exits_zero() {
    let dir = tmpdir("lint-clean");
    let input = dir.join("in.pgn");
    fs::write(
        &input,
        b"[Event \"x\"]\n[Site \"x\"]\n[Date \"2024.01.01\"]\n[Round \"1\"]\n[White \"a\"]\n[Black \"b\"]\n[Result \"1-0\"]\n\n1. e4 e5 2. Nf3 Nc6 1-0\n",
    )
    .unwrap();
    let (_stdout, _stderr, code) = run(&["lint", "--no-progress", input.to_str().unwrap()]);
    assert_eq!(code, 0);
}

#[test]
fn lint_json_emits_machine_readable_output() {
    let dir = tmpdir("lint-json");
    let input = dir.join("in.pgn");
    fs::write(
        &input,
        b"[Event \"x\"]\n[Site \"x\"]\n[Date \"2024.01.01\"]\n[Round \"1\"]\n[White \"a\"]\n[Black \"b\"]\n[Result \"1-0\"]\n\n1. e4 e5 1-0\n",
    )
    .unwrap();
    let (stdout, _stderr, _code) =
        run(&["lint", "--no-progress", "--json", input.to_str().unwrap()]);
    assert!(stdout.starts_with('{'));
    assert!(stdout.contains("\"games_checked\":1"));
    assert!(stdout.contains("\"issues\":["));
}

#[test]
fn fce_markers_exports_first_marker_position_as_jsonl() {
    let dir = tmpdir("fce-markers");
    let bucket = dir.join("LumbrasGigaBase_OTB_test");
    fs::create_dir_all(&bucket).unwrap();
    let input = bucket.join("1-4BN.pgn");
    let output = dir.join("markers.jsonl");
    fs::write(
        &input,
        b"[Event \"x\"]\n[Site \"s\"]\n[Date \"2026.05.14\"]\n[Round \"1\"]\n[White \"Alice\"]\n[Black \"Bob\"]\n[Result \"*\"]\n\n1. e4 { CQL } e5 { CQL } 2. Nf3 *\n",
    )
    .unwrap();

    let (stdout, stderr, code) = run(&[
        "fce-markers",
        "--no-progress",
        "--relative-to",
        dir.to_str().unwrap(),
        "-o",
        output.to_str().unwrap(),
        dir.to_str().unwrap(),
    ]);
    assert_eq!(code, 0, "stderr: {stderr}");
    assert_eq!(
        json_field(&stdout, "positions_written").as_deref(),
        Some("1")
    );

    let written = fs::read_to_string(&output).unwrap();
    assert_eq!(written.lines().count(), 1);
    assert!(written.contains("\"source_pgn\":\"LumbrasGigaBase_OTB_test.pgn\""));
    assert!(written.contains("\"output_pgn\":\"LumbrasGigaBase_OTB_test/1-4BN.pgn\""));
    assert!(written.contains("\"ending\":\"1-4BN\""));
    assert!(written.contains("\"move_uci\":\"e2e4\""));
    assert!(
        written.contains("\"fen\":\"rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1\"")
    );
}

#[test]
fn fce_markers_all_mode_keeps_later_markers() {
    let dir = tmpdir("fce-markers-all");
    let bucket = dir.join("Bucket");
    fs::create_dir_all(&bucket).unwrap();
    let input = bucket.join("9-2Qq.pgn");
    let output = dir.join("markers.jsonl");
    fs::write(
        &input,
        b"[Event \"x\"]\n[Result \"*\"]\n\n1. e4 {CQL} e5 {CQL} *\n",
    )
    .unwrap();

    let (_stdout, stderr, code) = run(&[
        "fce-markers",
        "--no-progress",
        "--mode",
        "all",
        "-o",
        output.to_str().unwrap(),
        bucket.to_str().unwrap(),
    ]);
    assert_eq!(code, 0, "stderr: {stderr}");

    let written = fs::read_to_string(&output).unwrap();
    assert_eq!(written.lines().count(), 2);
    assert!(written.contains("\"marker_index\":1"));
    assert!(written.contains("\"marker_index\":2"));
}

#[test]
fn fce_combined_markers_exports_stem_runs_and_tablebase_positions() {
    let dir = tmpdir("fce-combined-markers");
    let bucket = dir.join("LumbrasGigaBase_OTB_test");
    fs::create_dir_all(&bucket).unwrap();
    let input = bucket.join("fce-table-markers.pgn");
    let output = dir.join("facts.jsonl");
    fs::write(
        &input,
        b"[Event \"x\"]\n[Site \"s\"]\n[Date \"2026.05.15\"]\n[Round \"1\"]\n[White \"Alice\"]\n[Black \"Bob\"]\n[Result \"1-0\"]\n[FEN \"8/8/8/8/8/2k5/8/4K3 w - - 0 1\"]\n\n1. Ke2 {3-2NN} Kd4 {3-2NN 8-3RAra} 2. Kf3 {3-2NN} Ke5 {3-2NN} 1-0\n",
    )
    .unwrap();

    let (stdout, stderr, code) = run(&[
        "fce-combined-markers",
        "--no-progress",
        "--relative-to",
        dir.to_str().unwrap(),
        "--known-stems",
        "3-2NN,8-3RAra",
        "-o",
        output.to_str().unwrap(),
        dir.to_str().unwrap(),
    ]);
    assert_eq!(code, 0, "stderr: {stderr}");
    assert_eq!(
        json_field(&stdout, "game_stems_written").as_deref(),
        Some("2")
    );
    assert_eq!(
        json_field(&stdout, "positions_written").as_deref(),
        Some("2")
    );

    let written = fs::read_to_string(&output).unwrap();
    assert!(written.contains("\"kind\":\"game_stem\""));
    assert!(written.contains("\"kind\":\"position\""));
    assert!(written.contains("\"source_group\":\"otb\""));
    assert!(written.contains("\"stem\":\"3-2NN\""));
    assert!(written.contains("\"max_run_length\":4"));
    assert!(written.contains("\"run_length\":4"));
    assert!(written.contains("\"stem\":\"8-3RAra\""));
    assert!(written.contains("\"run_length\":1"));
}

#[test]
fn fce_combined_markers_can_write_sqlite_directly() {
    let sqlite_available = Command::new("sqlite3")
        .arg("-version")
        .stdin(Stdio::null())
        .output()
        .is_ok();
    if !sqlite_available {
        return;
    }

    let dir = tmpdir("fce-combined-markers-sqlite");
    let bucket = dir.join("LumbrasGigaBase_OTB_test");
    fs::create_dir_all(&bucket).unwrap();
    let input = bucket.join("fce-table-markers.pgn");
    let db = dir.join("facts.sqlite3");
    fs::write(
        &input,
        b"[Event \"x\"]\n[Site \"s\"]\n[Date \"2026.05.15\"]\n[Round \"1\"]\n[White \"Alice\"]\n[Black \"Bob\"]\n[Result \"1-0\"]\n[FEN \"8/8/8/8/8/2k5/8/N3K2B w - - 0 1\"]\n\n1. Ke2 {1-4BN} Kd4 {1-4BN} 1-0\n",
    )
    .unwrap();

    let (stdout, stderr, code) = run(&[
        "fce-combined-markers",
        "--no-progress",
        "--relative-to",
        dir.to_str().unwrap(),
        "--known-stems",
        "1-4BN",
        "--sqlite-db",
        db.to_str().unwrap(),
        "--profile-id",
        "fixture",
        dir.to_str().unwrap(),
    ]);
    assert_eq!(code, 0, "stderr: {stderr}");
    assert_eq!(
        json_field(&stdout, "game_stems_written").as_deref(),
        Some("1")
    );
    assert_eq!(
        json_field(&stdout, "positions_written").as_deref(),
        Some("1")
    );

    let query = "select (select count(*) from game_stems), (select count(*) from positions), (select count(*) from evaluations), (select material_side from game_stems limit 1), (select material_side from positions limit 1);";
    let output = Command::new("sqlite3")
        .arg(&db)
        .arg(query)
        .stdin(Stdio::null())
        .output()
        .expect("failed to query sqlite fixture");
    assert!(
        output.status.success(),
        "sqlite3 stderr: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert_eq!(stdout.trim(), "1|1|1|white|white");
}

#[test]
fn fce_combined_samples_exports_threshold_views() {
    let dir = tmpdir("fce-combined-samples");
    let otb = dir.join("LumbrasGigaBase_OTB_test");
    let online = dir.join("LumbrasGigaBase_Online_test");
    fs::create_dir_all(&otb).unwrap();
    fs::create_dir_all(&online).unwrap();
    fs::write(
        otb.join("fce-table-markers.pgn"),
        b"[Event \"otb\"]\n[Site \"s\"]\n[Date \"2026.05.15\"]\n[Round \"1\"]\n[White \"Alice\"]\n[Black \"Bob\"]\n[Result \"1-0\"]\n[FEN \"8/8/8/8/8/2k5/8/N3K2B w - - 0 1\"]\n\n1. Ke2 {1-4BN} Kd4 {1-4BN} 1-0\n",
    )
    .unwrap();
    fs::write(
        online.join("fce-table-markers.pgn"),
        b"[Event \"online\"]\n[Site \"s\"]\n[Date \"2026.05.15\"]\n[Round \"1\"]\n[White \"Carol\"]\n[Black \"Dan\"]\n[Result \"1/2-1/2\"]\n[FEN \"8/8/8/8/8/2k5/8/N3K2B w - - 0 1\"]\n\n1. Ke2 {1-4BN} Kd4 {1-4BN} 1/2-1/2\n",
    )
    .unwrap();
    let output = dir.join("samples.json");

    let (stdout, stderr, code) = run(&[
        "fce-combined-samples",
        "--no-progress",
        "--relative-to",
        dir.to_str().unwrap(),
        "--known-stems",
        "1-4BN",
        "--thresholds",
        "1,2",
        "--sample-size",
        "1",
        "-o",
        output.to_str().unwrap(),
        dir.to_str().unwrap(),
    ]);
    assert_eq!(code, 0, "stderr: {stderr}");
    assert_eq!(json_field(&stdout, "samples_seen").as_deref(), Some("4"));

    let written = fs::read_to_string(&output).unwrap();
    assert!(written.contains("\"kind\":\"fce-sampled-examples\""));
    assert!(written.contains("\"all\""));
    assert!(written.contains("\"otb\""));
    assert!(written.contains("\"online\""));
    assert!(written.contains("\"1-4BN\""));
    assert!(written.contains("\"available\":2"));
    assert!(written.contains("\"sampled\":1"));
    assert!(written.contains("\"fen\":\"8/8/8/8/8/2k5/4K3/N6B b - - 1 1\""));
    assert!(written.contains("\"runLength\":2"));
}

#[test]
fn fce_combined_openings_exports_eco_distribution() {
    let dir = tmpdir("fce-combined-openings");
    let otb = dir.join("LumbrasGigaBase_OTB_test");
    let online = dir.join("LumbrasGigaBase_Online_test");
    fs::create_dir_all(&otb).unwrap();
    fs::create_dir_all(&online).unwrap();
    fs::write(
        otb.join("fce-table-markers.pgn"),
        b"[Event \"otb\"]\n[Site \"s\"]\n[Date \"2026.05.15\"]\n[Round \"1\"]\n[White \"Alice\"]\n[Black \"Bob\"]\n[Result \"1-0\"]\n[ECO \"B90a\"]\n[FEN \"8/8/8/8/8/2k5/8/N3K2B w - - 0 1\"]\n\n1. Ke2 {1-4BN} Kd4 {1-4BN} 1-0\n",
    )
    .unwrap();
    fs::write(
        online.join("fce-table-markers.pgn"),
        b"[Event \"online\"]\n[Site \"s\"]\n[Date \"2026.05.15\"]\n[Round \"1\"]\n[White \"Carol\"]\n[Black \"Dan\"]\n[Result \"1/2-1/2\"]\n[ECO \"C42\"]\n[FEN \"8/8/8/8/8/2k5/8/N3K2B w - - 0 1\"]\n\n1. Ke2 {1-4BN} Kd4 {1-4BN} 1/2-1/2\n",
    )
    .unwrap();
    let output = dir.join("openings.json");

    let (stdout, stderr, code) = run(&[
        "fce-combined-openings",
        "--no-progress",
        "--relative-to",
        dir.to_str().unwrap(),
        "--known-stems",
        "1-4BN",
        "--thresholds",
        "1,2",
        "-o",
        output.to_str().unwrap(),
        dir.to_str().unwrap(),
    ]);
    assert_eq!(code, 0, "stderr: {stderr}");
    assert_eq!(
        json_field(&stdout, "opening_rows_seen").as_deref(),
        Some("4")
    );

    let written = fs::read_to_string(&output).unwrap();
    assert!(written.contains("\"kind\":\"fce-opening-ending-counts\""));
    assert!(written.contains("\"B90\""));
    assert!(written.contains("\"C42\""));
    assert!(written.contains("\"matchedRows\":1"));
    assert!(written.contains("\"sideWins\":1"));
    assert!(written.contains("\"sideDraws\":1"));
    assert!(written.contains("\"online\""));
}

#[test]
fn source_totals_counts_games_per_source_file() {
    let dir = tmpdir("source-totals");
    let corpus = dir.join("corpus");
    fs::create_dir_all(&corpus).unwrap();
    fs::write(
        corpus.join("LumbrasGigaBase_OTB_2025.pgn"),
        b"[Event \"a\"]\n[Result \"*\"]\n\n1. e4 *\n\n[Event \"b\"]\n[Result \"*\"]\n\n1. d4 *\n",
    )
    .unwrap();
    fs::write(
        corpus.join("LumbrasGigaBase_Online_2025.pgn"),
        b"[Event \"c\"]\n[Result \"*\"]\n\n1. c4 *\n",
    )
    .unwrap();
    let output = dir.join("source_totals.json");

    let (stdout, stderr, code) = run(&[
        "source-totals",
        "--no-progress",
        "-o",
        output.to_str().unwrap(),
        corpus.to_str().unwrap(),
    ]);
    assert_eq!(code, 0, "stdout: {stdout}\nstderr: {stderr}");
    assert!(
        stdout.is_empty(),
        "file output should not also print stdout"
    );

    let written = fs::read_to_string(&output).unwrap();
    assert!(written.contains("\"kind\":\"reti-pgn-source-totals\""));
    assert!(written.contains("\"totalGames\":3"));
    assert!(written.contains("\"otb\":2"));
    assert!(written.contains("\"online\":1"));
    assert!(written.contains("\"sourcePgn\":\"LumbrasGigaBase_OTB_2025.pgn\""));
    assert!(written.contains("\"games\":2"));
}

#[test]
fn unknown_flag_in_legacy_form_exits_nonzero() {
    let (_stdout, stderr, code) = run(&["--bogus-flag", "x", "y"]);
    assert_ne!(code, 0);
    assert!(stderr.contains("unknown option"));
}
