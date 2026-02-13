# Plot histograms (bar charts) of modem issues by device and by region, per symptom.
# Input: data/out/posts_modem_long.csv
# Output: data/out/modem_issue_by_device.png, data/out/modem_issue_by_region.png
# Run from project root: Rscript r/plot_issue_histograms.R

library(ggplot2)
library(dplyr)
library(readr)

if (!file.exists("data/out/posts_modem_long.csv")) {
  if (file.exists("../data/out/posts_modem_long.csv")) setwd("..")
  else stop("Run from project root. Missing data/out/posts_modem_long.csv")
}

csv_path <- "data/out/posts_modem_long.csv"
out_dir  <- "data/out"
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

d <- read_csv(csv_path, show_col_types = FALSE)
d$is_modem_issue <- as.logical(d$is_modem_issue)
d$symptom        <- as.character(d$symptom)
d$device         <- as.character(d$device)
d$region         <- as.character(d$region)

# Modem issues only, exclude "none"
modem <- d %>%
  filter(is_modem_issue == TRUE, symptom != "none") %>%
  distinct(post_id, symptom, device, region, .keep_all = FALSE)

# Replace empty/NA with "unknown" for cleaner display
modem$device <- ifelse(is.na(modem$device) | trimws(modem$device) == "", "unknown", modem$device)
modem$region <- ifelse(is.na(modem$region) | trimws(modem$region) == "", "unknown", modem$region)

if (nrow(modem) == 0) {
  message("No modem-issue data. Skipping histograms.")
  quit(save = "no", status = 0)
}

# ---- Bar chart by device, faceted by symptom ----
count_device <- modem %>%
  count(symptom, device, name = "n_posts")

p1 <- ggplot(count_device, aes(x = reorder(device, -n_posts), y = n_posts, fill = symptom)) +
  geom_col(position = "identity", show.legend = FALSE) +
  facet_wrap(~ symptom, scales = "free_y", ncol = 2) +
  labs(
    title = "Modem issues by device model (per symptom)",
    x = "Device", y = "Number of posts"
  ) +
  theme_minimal() +
  theme(
    axis.text.x = element_text(angle = 45, hjust = 1),
    strip.text = element_text(face = "bold")
  )
ggsave(file.path(out_dir, "modem_issue_by_device.png"), p1, width = 10, height = 6, dpi = 150)
message("Saved ", file.path(out_dir, "modem_issue_by_device.png"))

# ---- Bar chart by region, faceted by symptom ----
count_region <- modem %>%
  count(symptom, region, name = "n_posts")

p2 <- ggplot(count_region, aes(x = reorder(region, -n_posts), y = n_posts, fill = symptom)) +
  geom_col(position = "identity", show.legend = FALSE) +
  facet_wrap(~ symptom, scales = "free_y", ncol = 2) +
  labs(
    title = "Modem issues by region (per symptom)",
    x = "Region", y = "Number of posts"
  ) +
  theme_minimal() +
  theme(
    axis.text.x = element_text(angle = 45, hjust = 1),
    strip.text = element_text(face = "bold")
  )
ggsave(file.path(out_dir, "modem_issue_by_region.png"), p2, width = 10, height = 6, dpi = 150)
message("Saved ", file.path(out_dir, "modem_issue_by_region.png"))
