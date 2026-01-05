# Job Seeking Tool

An automated job search tool that scrapes intern/co-op positions from major tech companies, matches them against your resumes using ML-based similarity scoring, and generates organized Excel reports.

## Features

- **Multi-Company Scraping**: Supports 700+ companies across various ATS platforms:
  - Workday (428+ companies)
  - Greenhouse (37+ companies)
  - Lever, SmartRecruiters, and more
- **Resume Matching**: Uses sentence-transformers to compute similarity scores between job descriptions and your resumes
- **Smart Filtering**: Filter by job type (intern, co-op) and specialty (AI, ML, Data Science, etc.)
- **Auto-Discovery**: Automatically discovers career API endpoints from company lists
- **Categorized Results**: Separates companies by search status (success, no jobs, API error, no API found)
- **Excel Output**: Generates formatted Excel reports with job matches and company search results

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Or use the setup script:
```bash
chmod +x setup.sh
./setup.sh
```

### 2. Configure

Copy the example config and customize:
```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` to:
- Add your resume files
- Customize job title keywords
- Add/remove companies

### 3. Run

```bash
python run_job_search.py
```

Options:
```bash
python run_job_search.py --days 30           # Look back 30 days
python run_job_search.py --no-similarity     # Skip resume matching (faster)
python run_job_search.py --output-dir ./out  # Custom output directory
python run_job_search.py --verbose           # Enable debug logging
```

## Configuration

### Input Files (Optional)

| File | Description |
|------|-------------|
| `config.yaml` | Main configuration file |
| `companies.xlsx` | Additional company list for auto-discovery |
| `applied_positions.xlsx` | Track already applied positions |
| `company_api.xlsx` | Pre-mapped company API URLs |

### Resume Configuration

```yaml
resumes:
  resume_tech:
    path: "resume_tech.docx"
    description: "Technical/Engineering focus"
  resume_ds:
    path: "resume_ds.docx"
    description: "Data Science focus"
```

### Adding Companies

Companies can be added in three ways:

1. **From `company_apis.yaml`** (recommended - 473 pre-configured companies):
```yaml
# Copy companies from company_apis.yaml to your config.yaml
companies:
  # Paste from company_apis.yaml
  Nvidia:
    name: "Nvidia"
    api_url: "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"
    type: "workday"
```

2. **Manually in config.yaml** (with known API):
```yaml
companies:
  MyCompany:
    name: "My Company"
    api_url: "https://mycompany.wd5.myworkdayjobs.com/careers"
    type: "workday"
```

3. **Via Excel file** (auto-discovery):
Add company names to an Excel file and reference it:
```yaml
company_list_file: "companies.xlsx"
```

## Supported ATS Platforms

| Platform | API Format | Example |
|----------|------------|---------|
| Workday | `{company}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` | nvidia.wd5.myworkdayjobs.com |
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{company}/jobs` | boards.greenhouse.io/databricks |
| Lever | `api.lever.co/v0/postings/{company}` | api.lever.co/v0/postings/palantir |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/{company}/postings` | api.smartrecruiters.com/v1/companies/biogen |

## Output

### Job Matches Excel
- Company, Title, Location, URL
- Posted Date
- Similarity Score (if enabled)
- Recommended Resume

### Company Search Results Excel
Categorized sheets:
- **Success**: Companies with matching jobs
- **No Matching Jobs**: API worked but no relevant intern positions
- **API Error**: Connection or parsing failures
- **No API Found**: Companies without discoverable career APIs

## Project Structure

```
job_seeking/
├── run_job_search.py      # Main entry point
├── config.yaml            # Your configuration (git-ignored)
├── config.example.yaml    # Template configuration
├── company_apis.yaml      # 473 pre-configured company APIs
├── requirements.txt       # Python dependencies
├── src/
│   ├── scrapers.py        # Job scraping logic for various ATS
│   ├── similarity.py      # Resume-job matching
│   ├── output.py          # Excel generation
│   └── company_discovery.py # Auto-discover company APIs
├── output/                # Generated reports (git-ignored)
└── archive/               # Old outputs (git-ignored)
```

## Requirements

- Python 3.8+
- Dependencies: `requests`, `pandas`, `openpyxl`, `pyyaml`, `sentence-transformers`

## Tips

1. **First run**: Use `--no-similarity` for faster testing
2. **Rate limiting**: The tool includes delays between API calls to avoid being blocked
3. **Large company lists**: Auto-discovery may take time for 500+ companies
4. **API changes**: Some company APIs change frequently; check logs for errors

## License

MIT License
