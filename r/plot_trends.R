# Plot modem issue trends from posts_modem_long.csv.
# Run from project root: Rscript r/plot_trends.R
# Uses created_month (Asia/Seoul); missing months filled with zeros.

library(ggplot2)
library(dplyr)
library(readr)
library(lubridate)

# Run from project root so data/out/ is found
if (!file.exists("data/out/posts_modem_long.csv")) {
  if (file.exists("../data/out/posts_modem_long.csv")) setwd("..")
  else stop("Run from project root: cd pixel-modem-trend && Rscript r/plot_trends.R")
}

csv_path <- "data/out/posts_modem_long.csv"
out_dir  <- "data/out"

if (!file.exists(csv_path)) {
  stop("Missing ", csv_path, ". Run step 4 first: python scripts/04_build_csv_long.py")
}

d <- read_csv(csv_path, show_col_types = FALSE)

# Normalize: is_modem_issue can be "True"/"False" or TRUE/FALSE
d$is_modem_issue <- as.logical(d$is_modem_issue)
d$symptom       <- as.character(d$symptom)
d$created_month <- as.character(d$created_month)

# Modem issues only, exclude "none"
modem <- d %>%
  filter(is_modem_issue == TRUE, symptom != "none")

# ---- Chart 1: Monthly total modem issues (distinct posts), line + points ----
monthly_total <- modem %>%
  distinct(created_month, post_id) %>%
  count(created_month, name = "n_posts")

# Full month sequence and fill zeros
months_all <- unique(d$created_month)
months_all <- months_all[months_all != ""]
if (length(months_all) > 0) {
  months_all <- sort(months_all)
  full_months <- tibble(created_month = months_all)
  monthly_total <- full_months %>%
    left_join(monthly_total, by = "created_month") %>%
    mutate(n_posts = coalesce(n_posts, 0L))
}

if (nrow(monthly_total) > 0) {
  p1 <- ggplot(monthly_total, aes(x = created_month, y = n_posts, group = 1)) +
    geom_line(linewidth = 1) +
    geom_point(size = 3) +
    labs(title = "Monthly total modem issues (all symptoms)", x = "Month", y = "Number of posts") +
    theme_minimal() +
    theme(axis.text.x = element_text(angle = 45, hjust = 1))
  ggsave(file.path(out_dir, "modem_trend_monthly.png"), p1, width = 8, height = 5, dpi = 150)
  message("Saved data/out/modem_trend_monthly.png")
} else {
  # Empty plot so file exists
  monthly_total <- tibble(created_month = character(), n_posts = integer())
  p1 <- ggplot(monthly_total, aes(x = created_month, y = n_posts)) + geom_blank() +
    labs(title = "Monthly total modem issues", x = "Month", y = "Number of posts") + theme_minimal()
  ggsave(file.path(out_dir, "modem_trend_monthly.png"), p1, width = 8, height = 5, dpi = 150)
  message("No modem-issue data; saved empty chart data/out/modem_trend_monthly.png")
}

# ---- Chart 2: Top 6 symptoms by total count, monthly line chart ----
symptom_totals <- modem %>%
  count(symptom, name = "total") %>%
  slice_max(total, n = 6, with_ties = TRUE)
top_symptoms <- symptom_totals$symptom

monthly_by_symptom <- modem %>%
  filter(symptom %in% top_symptoms) %>%
  distinct(created_month, symptom, post_id) %>%
  count(created_month, symptom, name = "n_posts")

# Complete (month x top_symptom) with zeros (base R expand.grid -> tibble)
if (length(top_symptoms) > 0 && length(months_all) > 0) {
  full_grid <- as_tibble(expand.grid(
    created_month = months_all,
    symptom = top_symptoms,
    stringsAsFactors = FALSE
  ))
  monthly_by_symptom <- full_grid %>%
    left_join(monthly_by_symptom, by = c("created_month", "symptom")) %>%
    mutate(n_posts = coalesce(n_posts, 0L))
}

if (nrow(monthly_by_symptom) > 0) {
  p2 <- ggplot(monthly_by_symptom, aes(x = created_month, y = n_posts, colour = symptom, group = symptom)) +
    geom_line(linewidth = 1) +
    geom_point(size = 2) +
    labs(title = "Monthly modem issues by symptom (top 6)", x = "Month", y = "Number of posts", colour = "Symptom") +
    theme_minimal() +
    theme(axis.text.x = element_text(angle = 45, hjust = 1), legend.position = "bottom")
  ggsave(file.path(out_dir, "modem_symptoms_monthly.png"), p2, width = 9, height = 6, dpi = 150)
  message("Saved data/out/modem_symptoms_monthly.png")
} else {
  monthly_by_symptom <- tibble(created_month = character(), symptom = character(), n_posts = integer())
  p2 <- ggplot(monthly_by_symptom, aes(x = created_month, y = n_posts, colour = symptom)) + geom_blank() +
    labs(title = "Monthly symptoms (top 6)", x = "Month", y = "Number of posts") + theme_minimal()
  ggsave(file.path(out_dir, "modem_symptoms_monthly.png"), p2, width = 9, height = 6, dpi = 150)
  message("No symptom data; saved empty chart data/out/modem_symptoms_monthly.png")
}
