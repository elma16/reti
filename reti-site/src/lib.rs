pub mod aggregate;
pub mod catalog;
pub mod cli;
pub mod csv_export;
pub mod manifest;
pub mod opening_page;
pub mod openings;
pub mod pipeline;
pub mod render;
pub mod sankey;
pub mod source;
pub mod sqlite;

pub type SiteResult<T> = Result<T, SiteError>;

#[derive(Debug)]
pub struct SiteError {
    message: String,
}

impl SiteError {
    pub fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl std::fmt::Display for SiteError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for SiteError {}

impl From<std::io::Error> for SiteError {
    fn from(value: std::io::Error) -> Self {
        Self::new(value.to_string())
    }
}

impl From<serde_json::Error> for SiteError {
    fn from(value: serde_json::Error) -> Self {
        Self::new(value.to_string())
    }
}
