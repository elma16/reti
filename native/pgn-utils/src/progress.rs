//! Thin wrapper around `indicatif` that hides itself when stderr is not a TTY
//! or when the user passes `--no-progress`. All subcommands take a
//! [`ProgressReporter`] so they don't need to care about the difference.
//!
//! The wrapper exposes both byte-oriented and item-oriented progress so the
//! file-reading commands (clean/concat/dedup) can show bytes processed while
//! `lint` can also tick per-game when desirable.

use std::io::{self, IsTerminal, Read};

use indicatif::{ProgressBar, ProgressDrawTarget, ProgressStyle};

#[derive(Clone)]
pub struct ProgressReporter {
    bar: ProgressBar,
}

impl ProgressReporter {
    /// Create a byte-oriented reporter. When `enabled` is false (or stderr is
    /// not a TTY), the reporter becomes a silent no-op.
    pub fn bytes(total: u64, label: &str, enabled: bool) -> Self {
        let bar = if !enabled || !io::stderr().is_terminal() {
            ProgressBar::with_draw_target(Some(total), ProgressDrawTarget::hidden())
        } else {
            let bar = ProgressBar::new(total);
            bar.set_style(
                ProgressStyle::with_template(
                    "{msg} [{bar:40.cyan/blue}] {bytes}/{total_bytes} ({eta})",
                )
                .unwrap()
                .progress_chars("=>-"),
            );
            bar.set_message(label.to_string());
            bar
        };
        Self { bar }
    }

    /// Create a count-oriented reporter (e.g. games or files).
    pub fn items(total: u64, label: &str, enabled: bool) -> Self {
        let bar = if !enabled || !io::stderr().is_terminal() {
            ProgressBar::with_draw_target(Some(total), ProgressDrawTarget::hidden())
        } else {
            let bar = ProgressBar::new(total);
            bar.set_style(
                ProgressStyle::with_template("{msg} [{bar:40.cyan/blue}] {pos}/{len} ({eta})")
                    .unwrap()
                    .progress_chars("=>-"),
            );
            bar.set_message(label.to_string());
            bar
        };
        Self { bar }
    }

    /// Wrap a reader so every byte read advances the progress bar.
    pub fn wrap<R: Read>(&self, reader: R) -> ProgressRead<R> {
        ProgressRead {
            inner: reader,
            bar: self.bar.clone(),
        }
    }

    pub fn inc(&self, n: u64) {
        self.bar.inc(n);
    }

    pub fn finish(&self, msg: &str) {
        self.bar.finish_with_message(msg.to_string());
    }
}

/// Reader wrapper that increments a `ProgressBar` by the byte count returned
/// from each `read`. Used to drive byte-based progress without instrumenting
/// each subcommand's read loop.
pub struct ProgressRead<R: Read> {
    inner: R,
    bar: ProgressBar,
}

impl<R: Read> Read for ProgressRead<R> {
    fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
        let n = self.inner.read(buf)?;
        self.bar.inc(n as u64);
        Ok(n)
    }
}
