args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 2)
data <- read.csv(args[1], stringsAsFactors = FALSE)
primary <- data[data$scope == "primary" & data$pool_size == 30, ]
live <- data[data$scope == "common_live_timing" & data$pool_size == 30, ]
secondary <- data[data$scope == "same_question_secondary", ]
if (!nrow(primary) || !nrow(live) || !nrow(secondary)) {
    stop("Expected final primary, common live timing, and paired secondary results")
}

gate_methods <- c("full_sugeno_seed42", "fixed_fuzzy", "ridge", "qwen_selfcheck")
direct_methods <- c("top2", "direct_2plus4", "full", "v2_direct_2plus1")
method_names <- c("Sugeno", "Fixed Fuzzy", "Linear", "Qwen self-check", "Top-2", "Direct 2+4",
                  "Full", "V2 direct 2+1", "V2 adaptive")
names(method_names) <- c(gate_methods, direct_methods, "v2_native")
palette <- c("#15677B", "#197346", "#8A551C", "#663A75", "#849199", "#AD3D4C", "#424F57",
             "#A34F15", "#4159A0")
names(palette) <- names(method_names)
method_marks <- setNames(c(19, 17, 15, 18, 0, 4, 1, 5, 2), names(method_names))
font <- "sans"

png(args[2], width = 1820, height = 1500, res = 150, type = "cairo", bg = "white")
par(mfrow = c(2, 2), mar = c(4.6, 4.5, 3.1, 1.1), family = font, mgp = c(2.7, 0.7, 0), bty = "l")

display <- primary[primary$method %in% names(method_names), ]
plot(display$input_tokens_mean, 100*display$answer_f1_mean, type = "n", xlab = "Qwen input tokens per question",
     ylab = "Answer F1 (%)", main = "30 paragraphs: all final cases")
grid(col = "#DFE4E7", lty = 1)
for (method in names(method_names)) {
    rows <- display[display$method == method, ]
    rows <- rows[order(rows$budget_percent), ]
    lines(rows$input_tokens_mean, 100*rows$answer_f1_mean, type = "o", col = palette[method],
          lwd = 2, pch = method_marks[method])
}
legend("bottomright", method_names, bty = "n", pch = method_marks, col = palette, cex = 0.79, ncol = 2)

display <- live[live$method %in% names(method_names), ]
stopifnot(nrow(display) == length(method_names))
plot(display$live_path_seconds_mean, 100*display$answer_f1_mean, type = "n", xlab = "Measured live path (seconds)",
     ylab = "Answer F1 (%)", main = "30 paragraphs: common timing panel")
grid(col = "#DFE4E7", lty = 1)
for (method in names(method_names)) {
    row <- display[display$method == method, ]
    points(row$live_path_seconds_mean, 100*row$answer_f1_mean, col = palette[method], lwd = 2,
           cex = 1.3, pch = method_marks[method])
}
legend("top", method_names, inset = 0.08, bty = "n", pch = method_marks, col = palette,
       cex = 0.79, ncol = 2)

display <- secondary[secondary$method %in% c(gate_methods[c(1, 3)], direct_methods[c(2, 3)]) &
                     (is.na(secondary$budget_percent) | secondary$budget_percent == 20), ]
scale_plot <- function(metric, multiplier, label, title, legend_position) {
    plot(display$pool_size, multiplier*display[[metric]], type = "n", xaxt = "n",
         xlab = "Paragraphs in candidate pool", ylab = label, main = title)
    axis(1, at = c(10, 30, 60))
    grid(col = "#DFE4E7", lty = 1)
    for (method in unique(display$method)) {
        rows <- display[display$method == method, ]
        rows <- rows[order(rows$pool_size), ]
        lines(rows$pool_size, multiplier*rows[[metric]], type = "o", col = palette[method],
              lwd = 2, pch = method_marks[method])
    }
    legend(legend_position, method_names[unique(display$method)], bty = "n",
           pch = method_marks[unique(display$method)], col = palette[unique(display$method)], cex = 0.85)
}
scale_plot("answer_f1_mean", 100, "Answer F1 (%)", "Same 60 questions: quality by pool size", "topright")
scale_plot("input_tokens_mean", 1, "Qwen input tokens per question", "Same 60 questions: cost by pool size", "topleft")
invisible(dev.off())
