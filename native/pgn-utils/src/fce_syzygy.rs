//! Evaluate pending FCE tablebase rows in SQLite using Syzygy from Rust.

use std::ffi::{CStr, CString, OsString};
use std::os::raw::{c_char, c_int, c_void};
use std::path::{Path, PathBuf};
use std::ptr;
use std::thread;
use std::time::{SystemTime, UNIX_EPOCH};

use shakmaty::fen::Fen;
use shakmaty::{CastlingMode, Chess, Color, Position};
use shakmaty_syzygy::{Tablebase, Wdl};

use crate::cli;
use crate::progress::ProgressReporter;

const USAGE: &str = "\
usage: pgn-utils fce-syzygy-eval [options]

options:
  --db PATH               SQLite DB containing pending evaluations
  --syzygy-dir DIR        Syzygy WDL directory; can be repeated
  --max-pieces N          evaluate pending rows with <= N pieces (default: 5)
  --batch-rows N          rows per SQLite transaction (default: 10000)
  --workers N             Syzygy probe worker threads (default: 1)
  --max-evals N           stop after at most N evaluations
  --no-progress           disable the stderr progress bar";

#[derive(Debug, Clone)]
struct SyzygyEvalOptions {
    db_path: PathBuf,
    syzygy_dirs: Vec<PathBuf>,
    max_pieces: i64,
    batch_rows: i64,
    workers: usize,
    max_evals: Option<i64>,
    show_progress: bool,
}

#[derive(Debug, Default, Clone, Copy)]
struct SyzygyEvalStats {
    pending_before: i64,
    attempted: i64,
    ok: i64,
    errors: i64,
}

impl SyzygyEvalStats {
    fn to_json(self) -> String {
        format!(
            "{{\"mode\":\"fce-syzygy-eval\",\"pending_before\":{},\"attempted\":{},\"ok\":{},\"errors\":{}}}",
            self.pending_before, self.attempted, self.ok, self.errors
        )
    }
}

pub fn run_subcommand(args: &[OsString]) -> Result<(), String> {
    if args.iter().any(|arg| {
        let text = arg.to_string_lossy();
        text == "--help" || text == "-h" || text == "help"
    }) {
        println!("{USAGE}");
        return Ok(());
    }
    let parsed = cli::parse(
        args,
        &[],
        &[
            "db",
            "syzygy-dir",
            "max-pieces",
            "batch-rows",
            "workers",
            "max-evals",
        ],
    )
    .map_err(|e| format!("{e}\n{USAGE}"))?;

    let db_path = parsed
        .get_kv("db")
        .map(PathBuf::from)
        .ok_or_else(|| format!("fce-syzygy-eval: --db is required\n{USAGE}"))?;
    let syzygy_dirs: Vec<PathBuf> = parsed
        .kv_flags
        .iter()
        .filter(|(name, _)| name == "syzygy-dir")
        .map(|(_, value)| PathBuf::from(value))
        .collect();
    if syzygy_dirs.is_empty() {
        return Err(format!(
            "fce-syzygy-eval: --syzygy-dir is required\n{USAGE}"
        ));
    }
    let max_pieces = parse_optional_i64(&parsed, "max-pieces")?.unwrap_or(5);
    let batch_rows = parse_optional_i64(&parsed, "batch-rows")?.unwrap_or(10_000);
    let workers = parse_optional_usize(&parsed, "workers")?.unwrap_or(1);
    let max_evals = parse_optional_i64(&parsed, "max-evals")?;
    if max_pieces <= 0 {
        return Err("fce-syzygy-eval: --max-pieces must be positive".to_string());
    }
    if batch_rows <= 0 {
        return Err("fce-syzygy-eval: --batch-rows must be positive".to_string());
    }
    if workers == 0 {
        return Err("fce-syzygy-eval: --workers must be positive".to_string());
    }

    let stats = run_syzygy_eval(&SyzygyEvalOptions {
        db_path,
        syzygy_dirs,
        max_pieces,
        batch_rows,
        workers,
        max_evals,
        show_progress: !parsed.global.no_progress,
    })?;
    println!("{}", stats.to_json());
    Ok(())
}

fn run_syzygy_eval(opts: &SyzygyEvalOptions) -> Result<SyzygyEvalStats, String> {
    let mut tablebase = Tablebase::<Chess>::new();
    let mut added = 0usize;
    for dir in &opts.syzygy_dirs {
        added += tablebase
            .add_directory(dir)
            .map_err(|e| format!("failed to add Syzygy directory {}: {e}", dir.display()))?;
    }
    if added == 0 {
        return Err("no Syzygy table files were found".to_string());
    }

    let db = SqliteDb::open(&opts.db_path)?;
    db.exec_batch(
        "
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        PRAGMA temp_store=MEMORY;
        PRAGMA cache_size=-200000;
        PRAGMA locking_mode=EXCLUSIVE;
        ",
    )?;
    let pending_before = count_pending(&db, opts.max_pieces)?;
    let total = opts
        .max_evals
        .map_or(pending_before, |limit| pending_before.min(limit));
    let progress = ProgressReporter::items(total as u64, "rust syzygy eval", opts.show_progress);
    let mut stats = SyzygyEvalStats {
        pending_before,
        ..SyzygyEvalStats::default()
    };
    let mut remaining = opts.max_evals.unwrap_or(i64::MAX);

    let mut select = db.prepare(
        "
        SELECT eval_key, fen
        FROM evaluations
        WHERE eval_status = 'pending'
          AND piece_count <= ?
        ORDER BY piece_count, eval_key
        LIMIT ?
        ",
    )?;
    let mut update = db.prepare(
        "
        UPDATE evaluations
        SET eval_source = 'tablebase',
            winning_side = ?,
            tb_wdl = ?,
            tb_dtz = NULL,
            sf_cp_white = NULL,
            sf_mate_white = NULL,
            sf_time_seconds = NULL,
            draw_threshold_cp = NULL,
            eval_status = ?,
            error_message = ?,
            evaluated_at = ?
        WHERE eval_key = ?
        ",
    )?;

    while remaining > 0 {
        let limit = opts.batch_rows.min(remaining);
        let batch = fetch_batch(&mut select, opts.max_pieces, limit)?;
        if batch.is_empty() {
            break;
        }

        db.exec_batch("BEGIN IMMEDIATE TRANSACTION;")?;
        let results = evaluate_batch(&tablebase, batch, opts.workers);
        for (eval_key, result) in results {
            update_result(&mut update, &eval_key, &result)?;
            stats.attempted += 1;
            if result.eval_status == "ok" {
                stats.ok += 1;
            } else {
                stats.errors += 1;
            }
            progress.inc(1);
            remaining -= 1;
        }
        db.exec_batch("COMMIT;")?;
    }

    progress.finish("rust syzygy eval done");
    Ok(stats)
}

#[derive(Debug, Clone)]
struct EvalTask {
    eval_key: String,
    fen: String,
}

#[derive(Debug)]
struct EvalOutcome {
    winning_side: &'static str,
    tb_wdl: Option<i64>,
    eval_status: &'static str,
    error_message: String,
    evaluated_at: String,
}

fn evaluate_fen(tablebase: &Tablebase<Chess>, fen: &str) -> EvalOutcome {
    let evaluated_at = unix_timestamp_string();
    let parsed_fen = match Fen::from_ascii(fen.as_bytes()) {
        Ok(parsed) => parsed,
        Err(err) => {
            return EvalOutcome {
                winning_side: "unknown",
                tb_wdl: None,
                eval_status: "tablebase_error",
                error_message: format!("invalid FEN: {err}"),
                evaluated_at,
            }
        }
    };
    let pos = match parsed_fen.into_position(CastlingMode::Standard) {
        Ok(pos) => pos,
        Err(err) => {
            return EvalOutcome {
                winning_side: "unknown",
                tb_wdl: None,
                eval_status: "tablebase_error",
                error_message: format!("illegal FEN position: {err}"),
                evaluated_at,
            }
        }
    };

    match tablebase.probe_wdl_after_zeroing(&pos) {
        Ok(wdl) => {
            let value = wdl_to_i64(wdl);
            EvalOutcome {
                winning_side: classify_side_to_move_wdl(value, pos.turn()),
                tb_wdl: Some(value),
                eval_status: "ok",
                error_message: String::new(),
                evaluated_at,
            }
        }
        Err(err) => EvalOutcome {
            winning_side: "unknown",
            tb_wdl: None,
            eval_status: "tablebase_error",
            error_message: err.to_string(),
            evaluated_at,
        },
    }
}

fn evaluate_batch(
    tablebase: &Tablebase<Chess>,
    batch: Vec<EvalTask>,
    workers: usize,
) -> Vec<(String, EvalOutcome)> {
    if workers <= 1 || batch.len() < 1024 {
        return batch
            .into_iter()
            .map(|task| {
                let result = evaluate_fen(tablebase, &task.fen);
                (task.eval_key, result)
            })
            .collect();
    }

    let worker_count = workers.min(batch.len());
    let chunk_size = batch.len().div_ceil(worker_count);
    thread::scope(|scope| {
        let mut handles = Vec::new();
        for chunk in batch.chunks(chunk_size) {
            handles.push(scope.spawn(move || {
                chunk
                    .iter()
                    .map(|task| (task.eval_key.clone(), evaluate_fen(tablebase, &task.fen)))
                    .collect::<Vec<_>>()
            }));
        }
        let mut out = Vec::new();
        for handle in handles {
            out.extend(handle.join().expect("Syzygy worker thread panicked"));
        }
        out
    })
}

fn wdl_to_i64(wdl: Wdl) -> i64 {
    i32::from(wdl) as i64
}

fn classify_side_to_move_wdl(wdl: i64, turn: Color) -> &'static str {
    if wdl > 0 {
        color_name(turn)
    } else if wdl < 0 {
        color_name(!turn)
    } else {
        "draw"
    }
}

fn color_name(color: Color) -> &'static str {
    match color {
        Color::White => "white",
        Color::Black => "black",
    }
}

fn update_result(
    stmt: &mut SqliteStatement,
    eval_key: &str,
    result: &EvalOutcome,
) -> Result<(), String> {
    stmt.bind_text(1, result.winning_side)?;
    if let Some(wdl) = result.tb_wdl {
        stmt.bind_i64(2, wdl)?;
    } else {
        stmt.bind_null(2)?;
    }
    stmt.bind_text(3, result.eval_status)?;
    stmt.bind_text(4, &result.error_message)?;
    stmt.bind_text(5, &result.evaluated_at)?;
    stmt.bind_text(6, eval_key)?;
    stmt.step_done()?;
    stmt.reset_clear()
}

fn fetch_batch(
    stmt: &mut SqliteStatement,
    max_pieces: i64,
    limit: i64,
) -> Result<Vec<EvalTask>, String> {
    stmt.bind_i64(1, max_pieces)?;
    stmt.bind_i64(2, limit)?;
    let mut rows = Vec::new();
    loop {
        match stmt.step()? {
            SQLITE_ROW => rows.push(EvalTask {
                eval_key: stmt.column_text(0)?,
                fen: stmt.column_text(1)?,
            }),
            SQLITE_DONE => break,
            _ => unreachable!("SQLite step only returns ROW/DONE or error"),
        }
    }
    stmt.reset_clear()?;
    Ok(rows)
}

fn count_pending(db: &SqliteDb, max_pieces: i64) -> Result<i64, String> {
    let mut stmt = db.prepare(
        "
        SELECT COUNT(*)
        FROM evaluations
        WHERE eval_status = 'pending'
          AND piece_count <= ?
        ",
    )?;
    stmt.bind_i64(1, max_pieces)?;
    let rc = stmt.step()?;
    if rc != SQLITE_ROW {
        return Err("pending count query returned no row".to_string());
    }
    let count = stmt.column_i64(0);
    stmt.reset_clear()?;
    Ok(count)
}

fn unix_timestamp_string() -> String {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs().to_string())
        .unwrap_or_else(|_| "0".to_string())
}

fn parse_optional_i64(parsed: &cli::ParsedArgs, name: &str) -> Result<Option<i64>, String> {
    parsed
        .get_kv(name)
        .map(|value| {
            value
                .to_string_lossy()
                .parse::<i64>()
                .map_err(|e| format!("invalid --{name}: {e}"))
        })
        .transpose()
}

fn parse_optional_usize(parsed: &cli::ParsedArgs, name: &str) -> Result<Option<usize>, String> {
    parsed
        .get_kv(name)
        .map(|value| {
            value
                .to_string_lossy()
                .parse::<usize>()
                .map_err(|e| format!("invalid --{name}: {e}"))
        })
        .transpose()
}

#[repr(C)]
struct sqlite3 {
    _private: [u8; 0],
}

#[repr(C)]
struct sqlite3_stmt {
    _private: [u8; 0],
}

type SqliteDestructor = Option<unsafe extern "C" fn(*mut c_void)>;

const SQLITE_OK: c_int = 0;
const SQLITE_ROW: c_int = 100;
const SQLITE_DONE: c_int = 101;
const SQLITE_OPEN_READWRITE: c_int = 0x0000_0002;
const SQLITE_OPEN_NOMUTEX: c_int = 0x0000_8000;

#[link(name = "sqlite3")]
extern "C" {
    fn sqlite3_open_v2(
        filename: *const c_char,
        pp_db: *mut *mut sqlite3,
        flags: c_int,
        z_vfs: *const c_char,
    ) -> c_int;
    fn sqlite3_close(db: *mut sqlite3) -> c_int;
    fn sqlite3_errmsg(db: *mut sqlite3) -> *const c_char;
    fn sqlite3_exec(
        db: *mut sqlite3,
        sql: *const c_char,
        callback: Option<
            unsafe extern "C" fn(*mut c_void, c_int, *mut *mut c_char, *mut *mut c_char) -> c_int,
        >,
        arg: *mut c_void,
        errmsg: *mut *mut c_char,
    ) -> c_int;
    fn sqlite3_prepare_v2(
        db: *mut sqlite3,
        sql: *const c_char,
        n_byte: c_int,
        pp_stmt: *mut *mut sqlite3_stmt,
        pz_tail: *mut *const c_char,
    ) -> c_int;
    fn sqlite3_finalize(stmt: *mut sqlite3_stmt) -> c_int;
    fn sqlite3_step(stmt: *mut sqlite3_stmt) -> c_int;
    fn sqlite3_reset(stmt: *mut sqlite3_stmt) -> c_int;
    fn sqlite3_clear_bindings(stmt: *mut sqlite3_stmt) -> c_int;
    fn sqlite3_bind_int64(stmt: *mut sqlite3_stmt, idx: c_int, value: i64) -> c_int;
    fn sqlite3_bind_null(stmt: *mut sqlite3_stmt, idx: c_int) -> c_int;
    fn sqlite3_bind_text(
        stmt: *mut sqlite3_stmt,
        idx: c_int,
        value: *const c_char,
        n: c_int,
        destructor: SqliteDestructor,
    ) -> c_int;
    fn sqlite3_column_int64(stmt: *mut sqlite3_stmt, idx: c_int) -> i64;
    fn sqlite3_column_text(stmt: *mut sqlite3_stmt, idx: c_int) -> *const c_char;
}

fn sqlite_transient() -> SqliteDestructor {
    unsafe { std::mem::transmute::<isize, SqliteDestructor>(-1) }
}

struct SqliteDb {
    raw: *mut sqlite3,
}

impl SqliteDb {
    fn open(path: &Path) -> Result<Self, String> {
        if !path.exists() {
            return Err(format!("SQLite DB does not exist: {}", path.display()));
        }
        let path_text = path.to_string_lossy();
        let c_path = CString::new(path_text.as_bytes())
            .map_err(|_| format!("SQLite path contains NUL byte: {}", path.display()))?;
        let mut raw = ptr::null_mut();
        let rc = unsafe {
            sqlite3_open_v2(
                c_path.as_ptr(),
                &mut raw,
                SQLITE_OPEN_READWRITE | SQLITE_OPEN_NOMUTEX,
                ptr::null(),
            )
        };
        if rc != SQLITE_OK {
            let message = sqlite_error(raw);
            if !raw.is_null() {
                unsafe {
                    sqlite3_close(raw);
                }
            }
            return Err(format!(
                "failed to open SQLite DB {}: {message}",
                path.display()
            ));
        }
        Ok(Self { raw })
    }

    fn exec_batch(&self, sql: &str) -> Result<(), String> {
        let c_sql = CString::new(sql)
            .map_err(|_| "SQLite SQL text unexpectedly contains NUL byte".to_string())?;
        let rc = unsafe {
            sqlite3_exec(
                self.raw,
                c_sql.as_ptr(),
                None,
                ptr::null_mut(),
                ptr::null_mut(),
            )
        };
        if rc != SQLITE_OK {
            return Err(sqlite_error(self.raw));
        }
        Ok(())
    }

    fn prepare(&self, sql: &str) -> Result<SqliteStatement, String> {
        let c_sql = CString::new(sql)
            .map_err(|_| "SQLite SQL text unexpectedly contains NUL byte".to_string())?;
        let mut stmt = ptr::null_mut();
        let rc =
            unsafe { sqlite3_prepare_v2(self.raw, c_sql.as_ptr(), -1, &mut stmt, ptr::null_mut()) };
        if rc != SQLITE_OK {
            return Err(sqlite_error(self.raw));
        }
        Ok(SqliteStatement {
            db: self.raw,
            raw: stmt,
        })
    }
}

impl Drop for SqliteDb {
    fn drop(&mut self) {
        if !self.raw.is_null() {
            unsafe {
                sqlite3_close(self.raw);
            }
        }
    }
}

struct SqliteStatement {
    db: *mut sqlite3,
    raw: *mut sqlite3_stmt,
}

impl SqliteStatement {
    fn bind_text(&mut self, idx: c_int, value: &str) -> Result<(), String> {
        let c_value = CString::new(value.as_bytes())
            .map_err(|_| format!("SQLite text value for bind {idx} contains NUL byte"))?;
        let rc = unsafe {
            sqlite3_bind_text(
                self.raw,
                idx,
                c_value.as_ptr(),
                value.len() as c_int,
                sqlite_transient(),
            )
        };
        if rc != SQLITE_OK {
            return Err(sqlite_error(self.db));
        }
        Ok(())
    }

    fn bind_i64(&mut self, idx: c_int, value: i64) -> Result<(), String> {
        let rc = unsafe { sqlite3_bind_int64(self.raw, idx, value) };
        if rc != SQLITE_OK {
            return Err(sqlite_error(self.db));
        }
        Ok(())
    }

    fn bind_null(&mut self, idx: c_int) -> Result<(), String> {
        let rc = unsafe { sqlite3_bind_null(self.raw, idx) };
        if rc != SQLITE_OK {
            return Err(sqlite_error(self.db));
        }
        Ok(())
    }

    fn step(&mut self) -> Result<c_int, String> {
        let rc = unsafe { sqlite3_step(self.raw) };
        match rc {
            SQLITE_ROW | SQLITE_DONE => Ok(rc),
            _ => Err(sqlite_error(self.db)),
        }
    }

    fn step_done(&mut self) -> Result<(), String> {
        let rc = self.step()?;
        if rc != SQLITE_DONE {
            return Err("SQLite statement unexpectedly returned a row".to_string());
        }
        Ok(())
    }

    fn reset_clear(&mut self) -> Result<(), String> {
        let reset_rc = unsafe { sqlite3_reset(self.raw) };
        if reset_rc != SQLITE_OK {
            return Err(sqlite_error(self.db));
        }
        let clear_rc = unsafe { sqlite3_clear_bindings(self.raw) };
        if clear_rc != SQLITE_OK {
            return Err(sqlite_error(self.db));
        }
        Ok(())
    }

    fn column_i64(&self, idx: c_int) -> i64 {
        unsafe { sqlite3_column_int64(self.raw, idx) }
    }

    fn column_text(&self, idx: c_int) -> Result<String, String> {
        let ptr = unsafe { sqlite3_column_text(self.raw, idx) };
        if ptr.is_null() {
            return Ok(String::new());
        }
        Ok(unsafe { CStr::from_ptr(ptr).to_string_lossy().into_owned() })
    }
}

impl Drop for SqliteStatement {
    fn drop(&mut self) {
        if !self.raw.is_null() {
            unsafe {
                sqlite3_finalize(self.raw);
            }
        }
    }
}

fn sqlite_error(db: *mut sqlite3) -> String {
    if db.is_null() {
        return "unknown SQLite error".to_string();
    }
    unsafe {
        let ptr = sqlite3_errmsg(db);
        if ptr.is_null() {
            "unknown SQLite error".to_string()
        } else {
            CStr::from_ptr(ptr).to_string_lossy().into_owned()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classifies_wdl_from_side_to_move() {
        assert_eq!(classify_side_to_move_wdl(2, Color::White), "white");
        assert_eq!(classify_side_to_move_wdl(-2, Color::White), "black");
        assert_eq!(classify_side_to_move_wdl(1, Color::Black), "black");
        assert_eq!(classify_side_to_move_wdl(0, Color::Black), "draw");
    }

    #[test]
    fn parses_optional_i64() {
        let parsed = cli::parse(
            &[OsString::from("--batch-rows"), OsString::from("42")],
            &[],
            &["batch-rows"],
        )
        .unwrap();
        assert_eq!(parse_optional_i64(&parsed, "batch-rows").unwrap(), Some(42));
    }

    #[test]
    fn syzygy_dir_must_exist_when_counting_files() {
        assert!(!std::fs::metadata("/definitely/not/a/syzygy/dir").is_ok());
    }
}
