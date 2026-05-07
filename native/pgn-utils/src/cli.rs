//! Tiny dependency-free argument parser shared by all subcommands.
//!
//! We avoid `clap` to keep the binary small and the build fast. Every
//! subcommand uses the same convention: a stream of positionals plus simple
//! `--flag` / `--flag value` options. Unknown options are an error.

use std::ffi::OsString;
use std::path::PathBuf;

/// Options every subcommand understands.
#[derive(Debug, Default, Clone)]
pub struct GlobalOpts {
    pub no_progress: bool,
    pub json: bool,
}

/// Parsed arguments for a single subcommand. Keeps positionals and flags
/// separate so the caller can pull out what it needs.
#[derive(Debug, Default)]
pub struct ParsedArgs {
    pub positionals: Vec<PathBuf>,
    pub bool_flags: Vec<String>,
    pub kv_flags: Vec<(String, OsString)>,
    pub global: GlobalOpts,
}

impl ParsedArgs {
    pub fn has_flag(&self, name: &str) -> bool {
        self.bool_flags.iter().any(|f| f == name)
    }

    pub fn get_kv(&self, name: &str) -> Option<&OsString> {
        self.kv_flags
            .iter()
            .rev()
            .find(|(k, _)| k == name)
            .map(|(_, v)| v)
    }
}

/// Parse a flat stream of CLI args into [`ParsedArgs`].
///
/// `bool_options` are flags that take no value (e.g. `--clean`).
/// `kv_options` are flags that take a value (e.g. `--output X`, `--output=X`).
/// Anything not in either list and starting with `--` is an error.
pub fn parse(
    args: &[OsString],
    bool_options: &[&str],
    kv_options: &[&str],
) -> Result<ParsedArgs, String> {
    let mut out = ParsedArgs::default();
    let mut i = 0;
    while i < args.len() {
        let raw = args[i].to_string_lossy().into_owned();
        if raw == "--" {
            for rest in &args[i + 1..] {
                out.positionals.push(PathBuf::from(rest));
            }
            break;
        }
        // Accept both `--long` and `-x` forms; `-x` is treated as the option
        // named "x". A bare "-" is a positional (a stand-in for stdin in
        // some tools — we just store it).
        let stripped_opt: Option<&str> = if let Some(s) = raw.strip_prefix("--") {
            Some(s)
        } else if raw.len() >= 2 && raw.starts_with('-') {
            Some(&raw[1..])
        } else {
            None
        };
        if let Some(stripped) = stripped_opt {
            // Generic global flags handled here to avoid duplicating per-subcommand.
            if stripped == "no-progress" {
                out.global.no_progress = true;
                i += 1;
                continue;
            }
            if stripped == "json" {
                out.global.json = true;
                i += 1;
                continue;
            }

            // Support --flag=value form.
            let (name, inline_value) = match stripped.split_once('=') {
                Some((n, v)) => (n.to_string(), Some(OsString::from(v))),
                None => (stripped.to_string(), None),
            };

            if bool_options.contains(&name.as_str()) {
                if inline_value.is_some() {
                    return Err(format!("flag --{name} does not take a value"));
                }
                out.bool_flags.push(name);
                i += 1;
            } else if kv_options.contains(&name.as_str()) {
                let value = if let Some(v) = inline_value {
                    i += 1;
                    v
                } else {
                    if i + 1 >= args.len() {
                        return Err(format!("flag --{name} requires a value"));
                    }
                    let v = args[i + 1].clone();
                    i += 2;
                    v
                };
                out.kv_flags.push((name, value));
            } else {
                return Err(format!("unknown option --{name}"));
            }
        } else {
            out.positionals.push(PathBuf::from(&args[i]));
            i += 1;
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn os(s: &str) -> OsString {
        OsString::from(s)
    }

    #[test]
    fn parses_positionals_and_bool_flags() {
        let args = [os("--preserve-markup"), os("in.pgn"), os("out.pgn")];
        let parsed = parse(&args, &["preserve-markup"], &[]).unwrap();
        assert!(parsed.has_flag("preserve-markup"));
        assert_eq!(parsed.positionals.len(), 2);
    }

    #[test]
    fn parses_kv_flag_with_space() {
        let args = [os("--output"), os("out.pgn"), os("in.pgn")];
        let parsed = parse(&args, &[], &["output"]).unwrap();
        assert_eq!(parsed.get_kv("output").unwrap(), &os("out.pgn"));
        assert_eq!(parsed.positionals.len(), 1);
    }

    #[test]
    fn parses_kv_flag_with_equals() {
        let args = [os("--output=out.pgn"), os("in.pgn")];
        let parsed = parse(&args, &[], &["output"]).unwrap();
        assert_eq!(parsed.get_kv("output").unwrap(), &os("out.pgn"));
    }

    #[test]
    fn rejects_unknown_flag() {
        let args = [os("--bogus")];
        assert!(parse(&args, &[], &[]).is_err());
    }

    #[test]
    fn double_dash_terminates_options() {
        let args = [os("--"), os("--not-a-flag.pgn")];
        let parsed = parse(&args, &[], &[]).unwrap();
        assert_eq!(parsed.positionals.len(), 1);
    }

    #[test]
    fn captures_global_flags() {
        let args = [os("--no-progress"), os("--json"), os("file")];
        let parsed = parse(&args, &[], &[]).unwrap();
        assert!(parsed.global.no_progress);
        assert!(parsed.global.json);
    }
}
