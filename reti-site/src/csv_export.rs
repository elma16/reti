use std::fs;
use std::path::Path;

use crate::aggregate::Snapshot;
use crate::SiteResult;

pub fn write_summary_by_ending(snapshot: &Snapshot, path: &Path) -> SiteResult<()> {
    let mut out = String::from("view,threshold,stem,label,quantity,corpus_percentage,matched_share,actual_games,actual_win,actual_draw,actual_loss,actual_decisive,tb_positions,tb_win,tb_draw,tb_loss,tb_actual_win,tb_actual_draw,tb_actual_loss\n");
    for (view_key, view) in &snapshot.dataset_views.views {
        for (threshold, threshold_view) in &view.threshold_views {
            for row in &snapshot.rows {
                write_row(
                    &mut out,
                    view_key,
                    threshold,
                    &row.stem,
                    &row.label,
                    threshold_view.rows.get(&row.stem),
                );
                for aux in &row.auxiliary_rows {
                    write_row(
                        &mut out,
                        view_key,
                        threshold,
                        &aux.stem,
                        &aux.label,
                        threshold_view.rows.get(&aux.stem),
                    );
                }
            }
        }
    }
    fs::write(path, out)?;
    Ok(())
}

pub fn write_tablebase_wdl(snapshot: &Snapshot, path: &Path) -> SiteResult<()> {
    let mut out = String::from("view,threshold,stem,total_positions,side_wins,side_draws,side_losses,symmetric_decisive,unknown_positions,tb_actual_side_wins,tb_actual_side_draws,tb_actual_side_losses,tb_actual_symmetric_decisive\n");
    for (view_key, view) in &snapshot.dataset_views.views {
        for (threshold, threshold_view) in &view.threshold_views {
            for (stem, row) in &threshold_view.rows {
                let w = &row.tablebase_wdl;
                if w.total_positions == 0 {
                    continue;
                }
                out.push_str(&format!(
                    "{},{},{},{},{},{},{},{},{},{},{},{},{}\n",
                    csv(view_key),
                    csv(threshold),
                    csv(stem),
                    w.total_positions,
                    w.side_wins,
                    w.side_draws,
                    w.side_losses,
                    w.symmetric_decisive,
                    w.unknown_positions,
                    w.actual_side_wins,
                    w.actual_side_draws,
                    w.actual_side_losses,
                    w.actual_symmetric_decisive
                ));
            }
        }
    }
    fs::write(path, out)?;
    Ok(())
}

fn write_row(
    out: &mut String,
    view_key: &str,
    threshold: &str,
    stem: &str,
    label: &str,
    row: Option<&crate::aggregate::RowStats>,
) {
    let Some(row) = row else {
        return;
    };
    let w = &row.tablebase_wdl;
    let a = &row.actual_result;
    out.push_str(&format!(
        "{},{},{},{},{},{:.8},{:.8},{},{},{},{},{},{},{},{},{},{},{},{}\n",
        csv(view_key),
        csv(threshold),
        csv(stem),
        csv(label),
        row.quantity,
        row.percentage,
        row.matched_share,
        a.total_games,
        a.side_wins,
        a.side_draws,
        a.side_losses,
        a.symmetric_decisive,
        w.total_positions,
        w.side_wins,
        w.side_draws,
        w.side_losses,
        w.actual_side_wins,
        w.actual_side_draws,
        w.actual_side_losses,
    ));
}

fn csv(value: &str) -> String {
    if value.contains(',') || value.contains('"') || value.contains('\n') {
        format!("\"{}\"", value.replace('"', "\"\""))
    } else {
        value.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quotes_csv_fields() {
        assert_eq!(csv("a,b"), "\"a,b\"");
        assert_eq!(csv("plain"), "plain");
    }
}
