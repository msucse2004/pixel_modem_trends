# Word cloud from modem-issue results (modem_issue_summary.csv).
# Input: data/out/modem_issue_summary.csv (description_1..5, symptom, n_posts)
#       data/out/posts_modem_long.csv (issue_description) as fallback
# Output: data/out/modem_wordcloud.png, data/out/modem_wordcloud.pdf
# Run from project root: Rscript r/plot_wordcloud.R

library(wordcloud)
library(readr)
library(dplyr)
library(viridis)

# Paths
if (!file.exists("data/out/modem_issue_summary.csv")) {
  if (file.exists("../data/out/modem_issue_summary.csv")) setwd("..")
  else stop("Run from project root. Missing data/out/modem_issue_summary.csv")
}
out_dir <- "data/out"
input_summary <- "data/out/modem_issue_summary.csv"
input_long <- "data/out/posts_modem_long.csv"

# Config
max_words <- 200
top_n <- 200
width_px <- 1400
height_px <- 900
bg <- "white"

# Simple English stopwords to drop
stopwords_en <- c(
  "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of",
  "with", "by", "from", "as", "is", "was", "are", "were", "been", "be", "have",
  "has", "had", "do", "does", "did", "will", "would", "could", "should", "may",
  "might", "must", "shall", "can", "need", "this", "that", "these", "those",
  "i", "you", "he", "she", "it", "we", "they", "my", "your", "his", "her", "its",
  "our", "their", "me", "him", "them", "us", "it", "its", "just", "so", "if",
  "then", "than", "when", "what", "which", "who", "how", "all", "each", "every",
  "both", "few", "more", "most", "other", "some", "such", "no", "not", "only",
  "own", "same", "into", "out", "up", "down", "about", "after", "before", "between"
)

txt <- function(x) ifelse(is.na(x) | nchar(trimws(as.character(x))) == 0, "", as.character(x))

# 1) Primary: modem_issue_summary.csv (description_1..5 + symptom, weighted by n_posts)
parts <- character(0)
if (file.exists(input_summary)) {
  sum_df <- read_csv(input_summary, show_col_types = FALSE)
  sum_df <- sum_df[sum_df$symptom != "" & !is.na(sum_df$symptom), , drop = FALSE]
  desc_cols <- grep("^description_[0-9]+$", names(sum_df), value = TRUE)
  sum_parts <- character(nrow(sum_df))
  for (i in seq_len(nrow(sum_df))) {
    descs <- if (length(desc_cols) > 0) {
      vals <- unlist(sum_df[i, desc_cols])
      paste(txt(vals), collapse = " ")
    } else ""
    sym <- gsub("_", " ", txt(sum_df$symptom[i]))
    np <- as.integer(sum_df$n_posts[i]); n <- if (is.na(np) || np < 1) 1L else np
    sum_parts[i] <- paste(descs, paste(rep(sym, n), collapse = " "))
  }
  parts <- sum_parts
}

# 2) Fallback: posts_modem_long issue_description
if (length(parts) == 0 || all(trimws(parts) == "")) {
  if (file.exists(input_long)) {
    d <- read_csv(input_long, show_col_types = FALSE)
    d$is_modem_issue <- as.logical(d$is_modem_issue)
    modem <- d %>% filter(is_modem_issue == TRUE, symptom != "none", !is.na(symptom))
    if (nrow(modem) > 0) {
      symptom_words <- gsub("_", " ", modem$symptom)
      parts <- paste(txt(modem$issue_description), symptom_words, sep = " ")
    }
  }
}

full_text <- if (length(parts) > 0) paste(trimws(parts), collapse = " ") else ""
full_text <- gsub("\\s+", " ", full_text)

if (nchar(trimws(full_text)) == 0) {
  message("No modem-issue descriptions found. Creating placeholder word cloud.")
  full_text <- "modem connectivity signal data slow dropped service"
}

# Tokenize: lowercase, keep letters only, split on non-letters
full_text <- tolower(full_text)
full_text <- gsub("[^a-z ]", " ", full_text)
full_text <- gsub("\\s+", " ", trimws(full_text))
words <- unlist(strsplit(full_text, " "))
words <- words[nchar(words) >= 2]
words <- words[!words %in% stopwords_en]

if (length(words) == 0) {
  message("No tokens after filtering. Creating placeholder.")
  words <- c("modem", "connectivity", "signal", "data")
}

# Frequency table, sort, take top N
freq_tab <- sort(table(words), decreasing = TRUE)
freq_tab <- head(freq_tab, top_n)
freq_vec <- as.integer(freq_tab)
names(freq_vec) <- names(freq_tab)

# Symptom boost: make symptom names stand out prominently (n_posts * boost)
# Symptom -> readable label for wordcloud (underscore to space)
SYMPTOM_LABELS <- c(
  "slow_data_latency" = "slow data latency",
  "lost_connectivity" = "lost connectivity",
  "no_service" = "no service",
  "stuck_lte" = "stuck lte",
  "stuck_5g" = "stuck 5g",
  "roaming_handoff" = "roaming handoff",
  "low_signal" = "low signal",
  "missed_calls" = "missed calls"
)
SYMPTOM_BOOST <- 60
if (file.exists(input_summary)) {
  sum_df <- read_csv(input_summary, show_col_types = FALSE)
  sum_df <- sum_df[sum_df$symptom != "" & !is.na(sum_df$symptom), , drop = FALSE]
  for (i in seq_len(nrow(sum_df))) {
    sym <- txt(sum_df$symptom[i])
    label <- SYMPTOM_LABELS[sym]
    if (is.na(label)) label <- gsub("_", " ", tolower(sym))
    else label <- as.character(label)
    np <- max(1L, as.integer(sum_df$n_posts[i]), na.rm = TRUE)
    boost <- np * SYMPTOM_BOOST
    sym_words <- strsplit(label, "\\s+")[[1]]
    sym_words <- sym_words[nchar(sym_words) >= 1]
    for (w in sym_words) {
      current <- if (w %in% names(freq_vec)) freq_vec[w] else 0
      freq_vec[w] <- current + boost
    }
  }
}

if (length(freq_vec) == 0) {
  freq_vec <- c(1, 1, 1, 1)
  names(freq_vec) <- c("modem", "connectivity", "signal", "data")
}

# Sort again by freq (symptoms should be at top now)
freq_vec <- sort(freq_vec, decreasing = TRUE)
freq_vec <- head(freq_vec, top_n)

dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
ncol <- min(50, length(freq_vec))
cols <- viridis_pal(option = "plasma")(ncol)

# PNG
png(
  file.path(out_dir, "modem_wordcloud.png"),
  width = width_px,
  height = height_px,
  units = "px",
  res = 300,
  bg = bg
)
wordcloud(
  words = names(freq_vec),
  freq = freq_vec,
  max.words = max_words,
  random.order = FALSE,
  rot.per = 0.35,
  colors = cols,
  scale = c(4, 0.5)
)
dev.off()

# PDF (cairo for Windows)
cairo_pdf(
  file.path(out_dir, "modem_wordcloud.pdf"),
  width = width_px / 100,
  height = height_px / 100,
  bg = bg
)
wordcloud(
  words = names(freq_vec),
  freq = freq_vec,
  max.words = max_words,
  random.order = FALSE,
  rot.per = 0.35,
  colors = cols,
  scale = c(4, 0.5)
)
dev.off()

message("Saved ", file.path(out_dir, "modem_wordcloud.png"), " and .pdf")
