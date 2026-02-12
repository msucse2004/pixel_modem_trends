# Install required packages for plot_trends.R if missing.
# Run from project root: Rscript r/install_packages.R

required <- c("ggplot2", "dplyr", "readr", "lubridate", "wordcloud", "viridis")
missing <- required[!(required %in% installed.packages()[,"Package"])]
if (length(missing) > 0) {
  install.packages(missing, repos = "https://cloud.r-project.org")
  message("Installed: ", paste(missing, collapse = ", "))
} else {
  message("All required packages already installed.")
}
