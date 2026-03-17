# OneClickShell - Job Application Automation

A powerful automation tool for scraping job listings, parsing resumes using machine learning, scoring job matches, and automatically applying to relevant positions on job portals.

## Project Overview

OneClickShell is designed to streamline the job application process by:
- **Web Scraping**: Automatically crawls job portals (LinkedIn, Naukri, etc.) for new job listings
- **Resume Parsing**: Uses transformers and NLP models to extract and profile resume information
- **Job Matching**: Scores job relevance using semantic similarity and ML models
- **Auto-Apply**: Automatically fills and submits job application forms with intelligent response handling
- **Report Generation**: Creates interactive HTML reports of job crawl results and matches

## Features

- **Intelligent Job Crawling**: Pagination support and intelligent link extraction from job portals
- **Resume Processing**: Extracts text from PDFs and creates semantic embeddings
- **Smart Scoring**: Uses sentence transformers and embedding similarity for job matching
- **AI-Powered Auto-Application**: Integrates with Ollama for intelligent form filling
- **Caching System**: Maintains QA cache and master QA data for consistent responses
- **HTML Reports**: Generates beautiful, interactive reports of job data and matches
- **Multi-user Support**: Support for multiple user profiles and configurations

## Installation

### Prerequisites
- Python 3.11 or higher
- Google Chrome/Chromium browser (for web scraping)
- Windows 10+ (currently optimized for Windows)

### Setup Instructions

1. **Clone or download the project**
   ```
   cd oneClickShell
   ```

2. **Create and activate virtual environment**
   ```
   python -m venv resume_transformers
   .\resume_transformers\Scripts\activate.bat  # On Windows
   ```

3. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```

4. **Configure your settings**
   - Copy and modify `config.json` with your credentials and preferences
   - Update `resume_profile.json` or create a new profile for your resume

5. **Run the application**
   ```
   python main.py
   ```
   
   Or use the batch script on Windows:
   ```
   run_my_script.bat
   ```

## Project Structure

```
oneClickShell/
├── main.py                         # Main entry point
├── helpers.py                      # Web scraping and page navigation utilities
├── score.py                        # Job scoring and resume embedding logic
├── resume_parser.py                # Resume parsing and profile management
├── report.py                       # HTML report generation
│
├── config.json                     # Main configuration file
├── requirements.txt                # Python dependencies
├── run_my_script.bat               # Windows batch runner
│
├── AutoApply/                      # Auto-application module
│   ├── auto_apply_new.py           # Intelligent form filling and auto-apply logic
│   ├── qa_cache.json               # Cached Q&A responses
│   └── master_qa.json              # Master Q&A database
│
├── outputs/                        # Generated reports and job data
│   └── run_YYYYMMDD_HHMMSS/
│       ├── job_data_*.json         # Crawled job listings
│       └── job_crawl_summary_*.html # HTML reports
│
└── resume_transformers/            # Virtual environment (created on first run)
```

## Dependencies

### Core Dependencies
- **selenium** (4.29.0) - Browser automation for web scraping
- **requests** (2.32.3) - HTTP client library
- **PyYAML** (6.0.2) - YAML parsing for configuration

### Machine Learning & NLP
- **transformers** (4.52.4) - Hugging Face transformers for NLP tasks
- **sentence-transformers** (3.4.1) - Semantic similarity and embeddings
- **torch** (2.7.0) - PyTorch deep learning framework
- **scikit-learn** (1.6.1) - Machine learning utilities
- **tokenizers** (0.21.1) - Fast tokenization for transformers

### Data Processing
- **PyPDF2** (3.0.1) - PDF parsing and text extraction
- **numpy** (2.0.2) - Numerical computing
- **scipy** (1.13.1) - Scientific computing utilities
- **pandas** - Data manipulation (via scikit-learn dependency)

### AI & LLM
- **ollama** (0.5.3) - Access to local Ollama models for intelligent form filling

### Utilities
- **Pillow** (11.2.1) - Image processing
- **tqdm** (4.67.1) - Progress bars
- **httpx** (0.28.1) - Async HTTP client
- **pydantic** (2.11.7) - Data validation
- **pydantic-core** (2.33.2) - Core pydantic functionality

### Networking
- **urllib3** (2.4.0) - HTTP client pool
- **httpcore** (1.0.9) - HTTP core library
- **trio** (0.30.0) - Async I/O library
- **websocket-client** (1.8.0) - WebSocket client

### Other Dependencies
- **packaging** (25.0) - Package version handling
- **filelock** (3.18.0) - File locking utilities
- **certifi** (2025.4.26) - SSL certificate verification
- **idna** (3.10) - Internationalized domain names
- **Jinja2** (3.1.6) - Template rendering
- **MarkupSafe** (3.0.2) - Safe string escaping
- **typing-extensions** (4.14.0) - Typing utilities
- **attrs** (25.3.0) - Class definitions
- **networkx** (3.2.1) - Graph algorithms

See `requirements.txt` for the complete list with exact versions.

## Configuration

Create a `config.json` file in the root directory:

```json
{
  "job_portal": "naukri",
  "keywords": ["python", "data science", "machine learning"],
  "auto_apply": true,
  "headless_browser": false,
  "credentials": {
    "username": "your_email@example.com",
    "password": "your_password"
  }
}
```

Create a resume profile JSON file to define your resume information:

```json
{
  "name": "Your Name",
  "email": "your_email@example.com",
  "phone": "1234567890",
  "skills": ["Python", "Machine Learning", "Data Science"],
  "experience": "5 years"
}
```

## Usage

### Basic Job Crawling
```python
python main.py
```

### Auto-Apply to Jobs
Set `AUTO_APPLY = True` in `main.py` and run the script. The tool will:
1. Crawl job listings
2. Parse and score each job
3. Automatically fill and submit applications for matching jobs

## Output

All outputs are saved in the `outputs/` folder organized by timestamp:
- `job_data_YYYYMMDD_HHMMSS.json` - Full job listings data
- `job_crawl_summary_YYYYMMDD_HHMMSS.html` - Interactive HTML report

## Contributing

The project contains multiple modules designed for specific tasks:
- **helpers.py**: Add new scraping strategies or page navigation logic
- **score.py**: Implement new scoring algorithms or embedding methods
- **resume_parser.py**: Enhance resume parsing capabilities
- **AutoApply/auto_apply_new.py**: Improve form filling and auto-apply logic

## License

This project is provided as-is for academic and personal use.

## Notes

- The `resume_transformers/` folder is a Python virtual environment created automatically on first run
- Ensure Chrome/Chromium is installed for web scraping functionality
- The tool uses sentence-transformers for semantic job matching
- Auto-apply functionality uses Ollama for intelligent question answering
- All API keys and sensitive credentials should be stored in `config.json` (not included in version control)
