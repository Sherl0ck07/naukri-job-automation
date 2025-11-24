# OneClickShell - Naukri Job Crawler & Resume Matcher

**OneClickShell** is an automated job crawler and resume-to-job matching tool for Naukri.com. It scrapes job listings, computes similarity scores between your resume and job descriptions using NLP embeddings, and generates a detailed interactive HTML report for easy filtering and review.

---

## Features

- **Automated Job Scraping:** Uses Selenium to collect job listings from Naukri.com.
- **Resume Extraction:** Extracts text from PDF resumes.
- **Semantic Matching:** Computes similarity scores between your resume and job descriptions using [TechWolf/JobBERT-v2](https://huggingface.co/TechWolf/JobBERT-v2).
- **Parallel Processing:** Fast scoring with multi-threading.
- **Interactive HTML Report:** Filter jobs by score, skill match, external application, and more.

---

## Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/oneClickShell.git
   cd oneClickShell
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Download ChromeDriver:**  
   Ensure [ChromeDriver](https://chromedriver.chromium.org/downloads) is installed and matches your Chrome version.

4. **Configure your run:**
   - Edit `config.json` with your Naukri credentials and resume path.
   - Add job search links to `links.txt` (as a Python list of tuples).  
     Example:  
     ```python
     [[pagesToScrape, copiedUrl], [pagesToScrape, copiedUrl]]
     ```
     > Go to Naukri, perform a search with your keywords and filters, copy the top URL, and add it in the above format.

---

## Usage

```bash
python main.py
```

The script will:

1. Log in to Naukri.
2. Scrape job listings.
3. Compute similarity scores.
4. Generate an HTML report in the `outputs` folder.

---

## Output

- **Job Data JSON:**  
  `outputs/run_<timestamp>/job_data_<timestamp>.json`
- **HTML Report:**  
  `outputs/run_<timestamp>/job_crawl_summary_<run>_<timestamp>.html`

---

## File Structure

- `main.py` - Main runner script.  
- `helpers.py` - Scraping and scoring helper functions.  
- `score.py` - Embedding and similarity computation.  
- `report.py` - HTML report generator.  
- `config.json` - User configuration (credentials, resume path).  
- `links.txt` - List of job search URLs.

---

## Troubleshooting

- If jobs appear empty in the HTML, check your filters in `report.py`.  
- Ensure your resume PDF is readable and the path in `config.json` is correct.  
- For Selenium errors, confirm that ChromeDriver is installed and in your PATH.

---

## License

MIT License

---

**Contributions Welcome!**  
Feel free to open issues or submit pull requests.

