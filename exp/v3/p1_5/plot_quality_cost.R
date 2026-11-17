args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 2)
df <- read.csv(args[1], stringsAsFactors = FALSE)
methods <- c("top2", "top4", "top6", "full", "v2_direct_2plus1", "2plus1", "2plus2", "2plus4")
labels <- c("BM25 top-2", "BM25 top-4", "BM25 top-6", "Full", "V2 direct 2+1",
            "Two-stage 2+1", "Two-stage 2+2", "Two-stage 2+4")
palette <- c("#1F5C7A", "#2E7897", "#4195A2", "#243B53", "#678844", "#BA7424", "#AD4F33", "#7E3D69")
shapes <- c(16, 17, 15, 18, 1, 2, 0, 5)
stopifnot(setequal(df$route, methods))

png(args[2], width = 1750, height = 1750, res = 180, bg = "white")
layout(matrix(c(1, 2, 3, 4, 5, 6, 7, 7), nrow = 4, byrow = TRUE),
       heights = c(1, 1, 1, 0.25))
par(oma = c(1, 0.5, 5, 0.5), mar = c(4.2, 4.7, 2.3, 0.8),
    col.axis = "#323D4A", col.lab = "#192B3C", col.main = "#192B3C",
    mgp = c(2.6, 0.7, 0), bty = "l", las = 1, cex.axis = 0.9, cex.lab = 0.92)

y <- range(df$f1 * 100)
y_lim <- c(max(0, floor(y[1] / 5) * 5 - 2), min(100, ceiling(y[2] / 5) * 5 + 2))
for (scale in c(10, 30, 60)) {
  d <- df[df$pool_size == scale, ]
  idx <- match(d$route, methods)
  service <- if (scale < 60) "8192 / 4 GiB" else "16384 / 6 GiB"
  for (cost in c("input_tokens", "elapsed_seconds")) {
    x <- d[[cost]]
    xlabel <- if (cost == "input_tokens") "Mean total Qwen input tokens (log scale)" else "Mean route wall time (s)"
    plot(x, 100 * d$f1, type = "n", log = if (cost == "input_tokens") "x" else "",
         ylim = y_lim, xlab = xlabel, ylab = "Answer F1 (%)",
         main = sprintf("%d paragraphs  |  %s", scale, service))
    abline(h = axTicks(2), col = "#E5EAF0", lty = 1)
    points(x, 100 * d$f1, pch = shapes[idx], col = palette[idx], cex = 1.35, lwd = 1.6)
  }
}

par(mar = c(0, 0, 0, 0))
plot.new()
legend("center", legend = labels, col = palette, pch = shapes, ncol = 4,
       bty = "n", cex = 0.9, pt.cex = 1.2, pt.lwd = 1.6, x.intersp = 0.6)
mtext("P1.5 development panel", side = 3, outer = TRUE, line = 2.8, font = 2, cex = 1.45,
      col = "#192B3C")
mtext("50 paired questions per pool size  |  Compare costs within each service setting", side = 3,
      outer = TRUE, line = 1.1, cex = 0.9, col = "#536274")
invisible(dev.off())
