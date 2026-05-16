use std::ffi::{CStr, CString};
use std::os::raw::{c_char, c_int, c_void};
use std::path::Path;
use std::ptr;

use crate::{SiteError, SiteResult};

#[repr(C)]
struct sqlite3 {
    _private: [u8; 0],
}

#[repr(C)]
struct sqlite3_stmt {
    _private: [u8; 0],
}

type SqliteDestructor = Option<unsafe extern "C" fn(*mut c_void)>;

pub const SQLITE_ROW: c_int = 100;
pub const SQLITE_DONE: c_int = 101;
const SQLITE_OK: c_int = 0;
const SQLITE_OPEN_READWRITE: c_int = 0x0000_0002;
const SQLITE_OPEN_CREATE: c_int = 0x0000_0004;
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
    fn sqlite3_bind_text(
        stmt: *mut sqlite3_stmt,
        idx: c_int,
        value: *const c_char,
        n: c_int,
        destructor: SqliteDestructor,
    ) -> c_int;
    fn sqlite3_column_int64(stmt: *mut sqlite3_stmt, idx: c_int) -> i64;
    fn sqlite3_column_double(stmt: *mut sqlite3_stmt, idx: c_int) -> f64;
    fn sqlite3_column_text(stmt: *mut sqlite3_stmt, idx: c_int) -> *const c_char;
}

fn sqlite_transient() -> SqliteDestructor {
    unsafe { std::mem::transmute::<isize, SqliteDestructor>(-1) }
}

pub struct Db {
    raw: *mut sqlite3,
}

impl Db {
    pub fn open(path: &Path, create: bool) -> SiteResult<Self> {
        let c_path = CString::new(path.to_string_lossy().as_bytes()).map_err(|_| {
            SiteError::new(format!("SQLite path contains NUL byte: {}", path.display()))
        })?;
        let mut raw = ptr::null_mut();
        let mut flags = SQLITE_OPEN_READWRITE | SQLITE_OPEN_NOMUTEX;
        if create {
            flags |= SQLITE_OPEN_CREATE;
        }
        let rc = unsafe { sqlite3_open_v2(c_path.as_ptr(), &mut raw, flags, ptr::null()) };
        if rc != SQLITE_OK {
            let message = sqlite_error(raw);
            if !raw.is_null() {
                unsafe {
                    sqlite3_close(raw);
                }
            }
            return Err(SiteError::new(format!(
                "failed to open SQLite DB {}: {message}",
                path.display()
            )));
        }
        Ok(Self { raw })
    }

    pub fn exec(&self, sql: &str) -> SiteResult<()> {
        let c_sql = CString::new(sql)
            .map_err(|_| SiteError::new("SQLite SQL text unexpectedly contains NUL byte"))?;
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
            return Err(SiteError::new(sqlite_error(self.raw)));
        }
        Ok(())
    }

    pub fn prepare(&self, sql: &str) -> SiteResult<Statement> {
        let c_sql = CString::new(sql)
            .map_err(|_| SiteError::new("SQLite SQL text unexpectedly contains NUL byte"))?;
        let mut stmt = ptr::null_mut();
        let rc =
            unsafe { sqlite3_prepare_v2(self.raw, c_sql.as_ptr(), -1, &mut stmt, ptr::null_mut()) };
        if rc != SQLITE_OK {
            return Err(SiteError::new(sqlite_error(self.raw)));
        }
        Ok(Statement {
            db: self.raw,
            raw: stmt,
        })
    }
}

impl Drop for Db {
    fn drop(&mut self) {
        if !self.raw.is_null() {
            unsafe {
                sqlite3_close(self.raw);
            }
        }
    }
}

pub struct Statement {
    db: *mut sqlite3,
    raw: *mut sqlite3_stmt,
}

impl Statement {
    pub fn bind_i64(&mut self, idx: c_int, value: i64) -> SiteResult<()> {
        let rc = unsafe { sqlite3_bind_int64(self.raw, idx, value) };
        if rc != SQLITE_OK {
            return Err(SiteError::new(sqlite_error(self.db)));
        }
        Ok(())
    }

    pub fn bind_text(&mut self, idx: c_int, value: &str) -> SiteResult<()> {
        let c_value = CString::new(value.as_bytes()).map_err(|_| {
            SiteError::new(format!(
                "SQLite text value for bind {idx} contains NUL byte"
            ))
        })?;
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
            return Err(SiteError::new(sqlite_error(self.db)));
        }
        Ok(())
    }

    pub fn step(&mut self) -> SiteResult<c_int> {
        let rc = unsafe { sqlite3_step(self.raw) };
        match rc {
            SQLITE_ROW | SQLITE_DONE => Ok(rc),
            _ => Err(SiteError::new(sqlite_error(self.db))),
        }
    }

    pub fn reset_clear(&mut self) -> SiteResult<()> {
        let reset_rc = unsafe { sqlite3_reset(self.raw) };
        if reset_rc != SQLITE_OK {
            return Err(SiteError::new(sqlite_error(self.db)));
        }
        let clear_rc = unsafe { sqlite3_clear_bindings(self.raw) };
        if clear_rc != SQLITE_OK {
            return Err(SiteError::new(sqlite_error(self.db)));
        }
        Ok(())
    }

    pub fn column_i64(&self, idx: c_int) -> i64 {
        unsafe { sqlite3_column_int64(self.raw, idx) }
    }

    pub fn column_f64(&self, idx: c_int) -> f64 {
        unsafe { sqlite3_column_double(self.raw, idx) }
    }

    pub fn column_text(&self, idx: c_int) -> String {
        let ptr = unsafe { sqlite3_column_text(self.raw, idx) };
        if ptr.is_null() {
            String::new()
        } else {
            unsafe { CStr::from_ptr(ptr).to_string_lossy().into_owned() }
        }
    }
}

impl Drop for Statement {
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
