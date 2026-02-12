# Word cloud from modem-issue evidence text.
# Input: data/out/posts_modem_long.csv (uses is_modem_issue==TRUE, evidence + title)
# Output: data/out/modem_wordcloud.png, data/out/modem_wordcloud.pdf
# Run from project root: Rscript r/plot_wordcloud.R

library(wordcloud)
library(readr)
library(dplyr)
library(viridis)

# Paths
if (!file.exists("data/out/posts_modem_long.csv")) {
  if (file.exists("../data/out/posts_modem_long.csv")) setwd("..")
  else stop("Run from project root. Missing data/out/posts_modem_long.csv")
}
out_dir <- "data/out"
input_file <- "data/out/posts_modem_long.csv"

# Config (reference: keywords_analysis plot_wordcloud.R)
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

# Read long CSV
d <- read_csv(input_file, show_col_types = FALSE)
d$is_modem_issue <- as.logical(d$is_modem_issue)

# Only modem-issue rows, one row per post (avoid duplicate evidence)
modem <- d %>%
  filter(is_modem_issue == TRUE) %>%
  distinct(post_id, .keep_all = TRUE)

if (nrow(modem) == 0) {
  message("No modem-issue posts. Creating placeholder word cloud.")
  modem <- tibble(
    evidence_1 = "no modem issue data",
    evidence_2 = "", evidence_3 = "", title = ""
  )
}

# Collapse evidence + title into one text per post, then one big string
txt <- function(x) ifelse(is.na(x) | nchar(trimws(as.character(x))) == 0, "", as.character(x))
parts <- paste(
  txt(modem$title),
  txt(modem$evidence_1),
  txt(modem$evidence_2),
  txt(modem$evidence_3),
  sep = " "
)
full_text <- paste(trimws(parts), collapse = " ")
full_text <- gsub("\\s+", " ", full_text)

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

if (length(freq_vec) == 0) {
  freq_vec <- c(1, 1, 1, 1)
  names(freq_vec) <- c("modem", "connectivity", "signal", "data")
}

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
