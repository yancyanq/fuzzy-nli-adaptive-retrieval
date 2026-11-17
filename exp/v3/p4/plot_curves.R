args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 3)
history <- read.csv(args[1])
scores <- read.csv(args[2], stringsAsFactors = FALSE)
best <- which.min(history$val_mse)

blue <- "#14647C"
green <- "#367352"
gold <- "#9B5916"
gray <- "#697480"
png(args[3], width = 1800, height = 900, res = 150, type = "cairo", bg = "white")
par(mfrow = c(1, 2), mar = c(4.6, 4.5, 3.1, 1.5), family = "sans",
    mgp = c(2.6, 0.75, 0), bty = "l")
plot(history$epoch, history$val_mse, type = "n", xlab = "Epoch", ylab = "MSE",
     ylim = range(history$train_mse, history$val_mse), main = "Full Sugeno (seed 42)")
grid(col = "#DFE4E7", lty = 1)
lines(history$epoch, history$train_mse, col = gray, lwd = 2)
lines(history$epoch, history$val_mse, col = blue, lwd = 2.5)
abline(v = history$epoch[best], col = gray, lty = 3)
points(history$epoch[best], history$val_mse[best], pch = 19, col = blue)
legend("right", c("Training", "Validation", paste("Checkpoint, epoch", history$epoch[best])),
       col = c(gray, blue, gray), lwd = c(2, 2.5, 1), lty = c(1, 1, 3), bty = "n", cex = 0.87)

methods <- c("full_sugeno_seed42", "fixed_fuzzy", "constant_mean")
colors <- c(blue, green, gold)
shown <- scores[scores$method %in% methods, ]
anchors <- scores[scores$method %in% c("top2_always_a", "two_stage_always_b"), ]
plot(shown$qwen_input_tokens_per_question, 100 * shown$val_f1, type = "n",
     xlim = c(355, 1420), ylim = c(42.5, 63), xlab = "Qwen input tokens per question",
     ylab = "Validation answer F1 (%)", main = "P3 cost replay (50 validation questions)")
grid(col = "#DFE4E7", lty = 1)
for (i in seq_along(methods)) {
    series <- shown[shown$method == methods[i], ]
    series <- series[order(series$budget_percent), ]
    lines(series$qwen_input_tokens_per_question, 100 * series$val_f1,
          type = "o", col = colors[i], pch = c(19, 17, 15)[i], lwd = 2.3)
    if (i == 1) {
        text(series$qwen_input_tokens_per_question, 100 * series$val_f1,
             paste0(series$budget_percent, "%"), pos = c(3, 3, 3, 3), cex = 0.73, col = blue)
    }
}
points(anchors$qwen_input_tokens_per_question, 100 * anchors$val_f1, pch = 1, col = gray, lwd = 2)
text(anchors$qwen_input_tokens_per_question, 100 * anchors$val_f1,
     c("Always A", "Always B"), pos = c(3, 1), cex = 0.77, col = gray)
legend("bottomright", c("Full Sugeno / Ridge", "Fixed Fuzzy", "Constant mean"),
       col = colors, lwd = 2.3, pch = c(19, 17, 15), bty = "n", cex = 0.87)
invisible(dev.off())
