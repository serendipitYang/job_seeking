"""
Job scrapers for major tech companies.
Each scraper fetches job listings from company career pages/APIs.
"""

import requests
import json
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class JobPosting:
    """Represents a job posting."""
    company: str
    title: str
    location: str
    url: str
    posted_date: Optional[datetime] = None
    description: str = ""
    job_id: str = ""
    requirements: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "company": self.company,
            "title": self.title,
            "location": self.location,
            "url": self.url,
            "posted_date": self.posted_date.isoformat() if self.posted_date else None,
            "description": self.description,
            "job_id": self.job_id,
        }


class BaseScraper(ABC):
    """Base class for job scrapers."""

    def __init__(self, company_name: str, config: Dict):
        self.company_name = company_name
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })

    @abstractmethod
    def fetch_jobs(self, keywords: List[str], days_back: int = 7) -> List[JobPosting]:
        """Fetch job postings matching keywords from the last N days."""
        pass

    def matches_keywords(self, title: str, keywords: List[str]) -> bool:
        """Check if job title matches any of the keywords."""
        title_lower = title.lower()
        return any(kw.lower() in title_lower for kw in keywords)

    def is_within_days(self, posted_date: Optional[datetime], days_back: int) -> bool:
        """Check if the posting date is within the specified days."""
        if not posted_date:
            return True  # Include if date unknown
        cutoff = datetime.now() - timedelta(days=days_back)
        return posted_date >= cutoff


class GoogleScraper(BaseScraper):
    """Scraper for Google/Alphabet careers."""

    def fetch_jobs(self, keywords: List[str], days_back: int = 7) -> List[JobPosting]:
        jobs = []
        # Google careers API v3 - POST request with JSON payload
        base_url = "https://careers.google.com/api/v3/search/"

        # Search for intern positions with specialty keywords
        search_queries = ["intern machine learning", "intern data science", "intern AI",
                         "internship ML", "internship data", "intern research",
                         "intern software", "intern PhD", "intern applied science"]

        for query in search_queries:
            # Use POST with JSON payload as per Google's API
            payload = {
                "distance": 50,
                "hl": "en_US",
                "jlo": "en_US",
                "location": [{"country": "US"}],
                "q": query,
                "sort_by": "date",
                "page": 1,
                "page_size": 100,
            }

            try:
                # Try POST first
                self.session.headers.update({"Content-Type": "application/json"})
                response = self.session.post(base_url, json=payload, timeout=30)

                if response.status_code != 200:
                    # Try GET as fallback
                    params = {
                        "distance": "50",
                        "hl": "en_US",
                        "jlo": "en_US",
                        "location": "United States",
                        "q": query,
                        "sort_by": "date",
                        "page": 1,
                        "page_size": 100,
                    }
                    response = self.session.get(base_url, params=params, timeout=30)

                if response.status_code == 200:
                    try:
                        data = response.json()
                        job_list = data.get("jobs", data.get("results", []))
                        for job in job_list:
                            title = job.get("title", job.get("job_title", ""))
                            posted_date = None
                            pub_date = job.get("publish_date", job.get("posted_date"))
                            if pub_date:
                                try:
                                    posted_date = datetime.fromisoformat(pub_date.replace("Z", "+00:00")).replace(tzinfo=None)
                                except:
                                    pass

                            if self.is_within_days(posted_date, days_back):
                                job_id = job.get("id", job.get("job_id", ""))
                                job_posting = JobPosting(
                                    company=self.company_name,
                                    title=title,
                                    location=", ".join(job.get("locations", [])) if isinstance(job.get("locations"), list) else str(job.get("locations", "")),
                                    url=f"https://careers.google.com/jobs/results/{job_id}" if job_id else "https://careers.google.com/jobs",
                                    posted_date=posted_date,
                                    description=job.get("description", ""),
                                    job_id=job_id,
                                )
                                jobs.append(job_posting)
                    except json.JSONDecodeError:
                        logger.debug(f"Google API returned non-JSON response")
                else:
                    logger.debug(f"Google API returned {response.status_code}")
            except Exception as e:
                logger.error(f"Error fetching Google jobs: {e}")

        # Log if no jobs found - API may have changed
        if not jobs:
            logger.warning("Google careers API may have changed - no jobs found. Check https://careers.google.com manually.")

        return jobs


class AmazonScraper(BaseScraper):
    """Scraper for Amazon careers."""

    def fetch_jobs(self, keywords: List[str], days_back: int = 7) -> List[JobPosting]:
        jobs = []
        base_url = "https://www.amazon.jobs/en/search.json"

        search_terms = ["intern", "internship", "co-op"]

        for term in search_terms:
            params = {
                "radius": "24km",
                "facets[]": ["location", "business_category", "category", "schedule_type_id"],
                "offset": 0,
                "result_limit": 100,
                "sort": "recent",
                "base_query": term,
                "country": "USA",
            }

            try:
                response = self.session.get(base_url, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    for job in data.get("jobs", []):
                        title = job.get("title", "")
                        if self.matches_keywords(title, keywords):
                            posted_date = None
                            date_str = job.get("posted_date")
                            if date_str:
                                try:
                                    posted_date = datetime.strptime(date_str, "%B %d, %Y")
                                except:
                                    try:
                                        posted_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                                    except:
                                        pass

                            if self.is_within_days(posted_date, days_back):
                                job_posting = JobPosting(
                                    company=self.company_name,
                                    title=title,
                                    location=job.get("location", ""),
                                    url=f"https://www.amazon.jobs{job.get('job_path', '')}",
                                    posted_date=posted_date,
                                    description=job.get("description", ""),
                                    job_id=job.get("id_icims", ""),
                                )
                                jobs.append(job_posting)
            except Exception as e:
                logger.error(f"Error fetching Amazon jobs: {e}")

        return jobs


class AppleScraper(BaseScraper):
    """Scraper for Apple careers."""

    def fetch_jobs(self, keywords: List[str], days_back: int = 7) -> List[JobPosting]:
        jobs = []
        base_url = "https://jobs.apple.com/api/role/search"

        search_queries = ["intern", "internship"]

        for query in search_queries:
            payload = {
                "query": query,
                "filters": {
                    "range": {
                        "standardWeeklyHours": {"start": None, "end": None}
                    }
                },
                "page": 1,
                "locale": "en-us",
                "sort": "newest"
            }

            try:
                self.session.headers.update({"Content-Type": "application/json"})
                response = self.session.post(base_url, json=payload, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    for job in data.get("searchResults", []):
                        title = job.get("postingTitle", "")
                        if self.matches_keywords(title, keywords):
                            posted_date = None
                            date_str = job.get("postingDate")
                            if date_str:
                                try:
                                    posted_date = datetime.strptime(date_str, "%Y-%m-%d")
                                except:
                                    pass

                            if self.is_within_days(posted_date, days_back):
                                job_posting = JobPosting(
                                    company=self.company_name,
                                    title=title,
                                    location=", ".join(job.get("locations", {}).get("name", [])) if isinstance(job.get("locations"), dict) else str(job.get("locations", "")),
                                    url=f"https://jobs.apple.com/en-us/details/{job.get('positionId', '')}",
                                    posted_date=posted_date,
                                    description=job.get("jobSummary", ""),
                                    job_id=job.get("positionId", ""),
                                )
                                jobs.append(job_posting)
            except Exception as e:
                logger.error(f"Error fetching Apple jobs: {e}")

        return jobs


class MetaScraper(BaseScraper):
    """Scraper for Meta/Facebook careers."""

    def fetch_jobs(self, keywords: List[str], days_back: int = 7) -> List[JobPosting]:
        jobs = []
        base_url = "https://www.metacareers.com/graphql"

        # Meta uses GraphQL - we'll try a simplified approach
        search_terms = ["intern", "internship"]

        for term in search_terms:
            try:
                # Fallback to web scraping approach
                careers_url = f"https://www.metacareers.com/jobs?q={term}&sort_by_new=true"
                response = self.session.get(careers_url, timeout=30)

                if response.status_code == 200:
                    # Try to extract job data from page
                    text = response.text
                    # Look for JSON data in script tags
                    pattern = r'\"jobId\":\"(\d+)\",\"title\":\"([^\"]+)\"'
                    matches = re.findall(pattern, text)

                    for job_id, title in matches:
                        if self.matches_keywords(title, keywords):
                            job_posting = JobPosting(
                                company=self.company_name,
                                title=title,
                                location="Various",
                                url=f"https://www.metacareers.com/jobs/{job_id}",
                                posted_date=None,
                                job_id=job_id,
                            )
                            jobs.append(job_posting)
            except Exception as e:
                logger.error(f"Error fetching Meta jobs: {e}")

        return jobs


class MicrosoftScraper(BaseScraper):
    """Scraper for Microsoft careers."""

    def fetch_jobs(self, keywords: List[str], days_back: int = 7) -> List[JobPosting]:
        jobs = []
        base_url = "https://gcsservices.careers.microsoft.com/search/api/v1/search"

        search_terms = ["intern", "internship"]

        for term in search_terms:
            params = {
                "q": term,
                "pg": 1,
                "pgSz": 100,
                "o": "Recent",
                "flt": "true",
            }

            try:
                response = self.session.get(base_url, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    for job in data.get("operationResult", {}).get("result", {}).get("jobs", []):
                        title = job.get("title", "")
                        if self.matches_keywords(title, keywords):
                            posted_date = None
                            date_str = job.get("postingDate")
                            if date_str:
                                try:
                                    posted_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                                except:
                                    pass

                            if self.is_within_days(posted_date, days_back):
                                job_posting = JobPosting(
                                    company=self.company_name,
                                    title=title,
                                    location=", ".join(job.get("properties", {}).get("locations", [])),
                                    url=f"https://careers.microsoft.com/us/en/job/{job.get('jobId', '')}",
                                    posted_date=posted_date,
                                    description=job.get("description", ""),
                                    job_id=job.get("jobId", ""),
                                )
                                jobs.append(job_posting)
            except Exception as e:
                logger.error(f"Error fetching Microsoft jobs: {e}")

        return jobs


class NvidiaScraper(BaseScraper):
    """Scraper for Nvidia careers (Workday)."""

    def fetch_jobs(self, keywords: List[str], days_back: int = 7) -> List[JobPosting]:
        jobs = []
        base_url = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs"

        # Update headers for Workday API
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://nvidia.wd5.myworkdayjobs.com",
            "Referer": "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
        })

        payload = {
            "appliedFacets": {},
            "limit": 100,
            "offset": 0,
            "searchText": "intern",
        }

        try:
            time.sleep(1)  # Rate limiting
            response = self.session.post(base_url, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                for job in data.get("jobPostings", []):
                    title = job.get("title", "")
                    # Check if it's an intern position AND matches specialty keywords
                    is_intern = any(t in title.lower() for t in ["intern", "co-op", "coop"])
                    matches_specialty = self.matches_keywords(title, keywords)

                    if is_intern and matches_specialty:
                        posted_date = None
                        date_str = job.get("postedOn", "")
                        if date_str:
                            try:
                                if "Today" in date_str:
                                    posted_date = datetime.now()
                                elif "Yesterday" in date_str:
                                    posted_date = datetime.now() - timedelta(days=1)
                                elif "Days Ago" in date_str:
                                    match = re.search(r'(\d+)', date_str)
                                    if match:
                                        days = int(match.group(1))
                                        posted_date = datetime.now() - timedelta(days=days)
                            except:
                                pass

                        # Include job regardless of date - we'll note date in output
                        external_path = job.get("externalPath", "")
                        job_posting = JobPosting(
                            company=self.company_name,
                            title=title,
                            location=job.get("locationsText", ""),
                            url=f"https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite{external_path}",
                            posted_date=posted_date,
                            job_id=external_path,
                        )
                        jobs.append(job_posting)
            else:
                logger.warning(f"Nvidia API returned {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching Nvidia jobs: {e}")

        return jobs


class TeslaScraper(BaseScraper):
    """Scraper for Tesla careers."""

    def fetch_jobs(self, keywords: List[str], days_back: int = 7) -> List[JobPosting]:
        jobs = []
        base_url = "https://www.tesla.com/cua-api/apps/careers/state"

        try:
            response = self.session.get(base_url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                for job in data.get("listings", []):
                    title = job.get("title", "")
                    # Tesla has different job structure
                    if "intern" in title.lower() or "internship" in title.lower():
                        if self.matches_keywords(title, keywords):
                            posted_date = None
                            date_str = job.get("postingDate") or job.get("createdDate")
                            if date_str:
                                try:
                                    posted_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                                except:
                                    pass

                            if self.is_within_days(posted_date, days_back):
                                job_posting = JobPosting(
                                    company=self.company_name,
                                    title=title,
                                    location=job.get("location", ""),
                                    url=f"https://www.tesla.com/careers/search/job/{job.get('id', '')}",
                                    posted_date=posted_date,
                                    description=job.get("description", ""),
                                    job_id=str(job.get("id", "")),
                                )
                                jobs.append(job_posting)
        except Exception as e:
            logger.error(f"Error fetching Tesla jobs: {e}")

        return jobs


class GenericWorkdayScraper(BaseScraper):
    """Generic scraper for Workday-based career sites."""

    def __init__(self, company_name: str, config: Dict, workday_url: str):
        super().__init__(company_name, config)
        self.original_url = workday_url
        # Convert URL to API format
        # Input: https://asml.wd3.myworkdayjobs.com/ASML
        # API:   https://asml.wd3.myworkdayjobs.com/wday/cxs/asml/ASML/jobs
        self.api_url, self.base_url = self._parse_workday_url(workday_url)

    def _parse_workday_url(self, url: str) -> tuple:
        """Parse Workday URL to get API endpoint and base URL for job links."""
        import re

        # Already an API URL
        if "/wday/cxs/" in url:
            base = url.rsplit("/wday", 1)[0]
            api = url if url.endswith("/jobs") else f"{url}/jobs"
            return api, base

        # Parse URL like https://company.wd1.myworkdayjobs.com/Site
        match = re.match(r'https://([^.]+)\.(wd\d+)\.myworkdayjobs\.com/([^/]+)/?', url)
        if match:
            tenant = match.group(1)
            wd_num = match.group(2)
            site = match.group(3)
            base_url = f"https://{tenant}.{wd_num}.myworkdayjobs.com"
            api_url = f"{base_url}/wday/cxs/{tenant}/{site}/jobs"
            return api_url, base_url

        # Fallback - try to construct API URL
        # Remove trailing slash and /jobs if present
        url = url.rstrip('/')
        if url.endswith('/jobs'):
            url = url[:-5]

        base_url = url
        api_url = f"{url}/jobs"
        return api_url, base_url

    def fetch_jobs(self, keywords: List[str], days_back: int = 7) -> List[JobPosting]:
        jobs = []

        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

        payload = {
            "appliedFacets": {},
            "limit": 100,
            "offset": 0,
            "searchText": "intern",
        }

        try:
            time.sleep(0.3)  # Rate limiting
            response = self.session.post(self.api_url, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                for job in data.get("jobPostings", []):
                    title = job.get("title", "")
                    title_lower = title.lower()
                    is_intern = any(t in title_lower for t in ["intern", "co-op", "coop", "internship"])
                    matches_specialty = self.matches_keywords(title, keywords)

                    if is_intern and matches_specialty:
                        external_path = job.get("externalPath", "")
                        job_posting = JobPosting(
                            company=self.company_name,
                            title=title,
                            location=job.get("locationsText", ""),
                            url=f"{self.base_url}{external_path}",
                            job_id=external_path,
                        )
                        jobs.append(job_posting)
            elif response.status_code == 404:
                # API URL may be incorrect, log for debugging
                logger.debug(f"{self.company_name} Workday API not found at {self.api_url}")
            else:
                logger.debug(f"{self.company_name} Workday API returned {response.status_code}")
        except Exception as e:
            logger.debug(f"Error fetching {self.company_name} jobs: {e}")

        return jobs


class GreenhouseScraper(BaseScraper):
    """Generic scraper for Greenhouse-based career sites."""

    def __init__(self, company_name: str, config: Dict, greenhouse_board: str):
        super().__init__(company_name, config)
        # Extract board name from URL like "https://boards.greenhouse.io/company"
        if "greenhouse.io/" in greenhouse_board:
            self.board_name = greenhouse_board.split("greenhouse.io/")[-1].split("/")[0]
        else:
            self.board_name = greenhouse_board
        self.api_url = f"https://boards-api.greenhouse.io/v1/boards/{self.board_name}/jobs"

    def fetch_jobs(self, keywords: List[str], days_back: int = 7) -> List[JobPosting]:
        jobs = []

        try:
            time.sleep(0.5)
            response = self.session.get(self.api_url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                for job in data.get("jobs", []):
                    title = job.get("title", "")
                    title_lower = title.lower()
                    is_intern = any(t in title_lower for t in ["intern", "co-op", "coop", "internship"])
                    matches_specialty = self.matches_keywords(title, keywords)

                    if is_intern and matches_specialty:
                        # Parse date
                        posted_date = None
                        updated_at = job.get("updated_at")
                        if updated_at:
                            try:
                                posted_date = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).replace(tzinfo=None)
                            except:
                                pass

                        location = job.get("location", {})
                        if isinstance(location, dict):
                            location = location.get("name", "")

                        job_posting = JobPosting(
                            company=self.company_name,
                            title=title,
                            location=str(location),
                            url=job.get("absolute_url", ""),
                            posted_date=posted_date,
                            job_id=str(job.get("id", "")),
                        )
                        jobs.append(job_posting)
            else:
                logger.debug(f"{self.company_name} Greenhouse API returned {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching {self.company_name} jobs: {e}")

        return jobs


class LeverScraper(BaseScraper):
    """Generic scraper for Lever-based career sites."""

    def __init__(self, company_name: str, config: Dict, lever_url: str):
        super().__init__(company_name, config)
        # Extract company from URL like "https://jobs.lever.co/company"
        if "lever.co/" in lever_url:
            self.company_slug = lever_url.split("lever.co/")[-1].split("/")[0]
        else:
            self.company_slug = lever_url
        self.api_url = f"https://api.lever.co/v0/postings/{self.company_slug}"

    def fetch_jobs(self, keywords: List[str], days_back: int = 7) -> List[JobPosting]:
        jobs = []

        try:
            time.sleep(0.5)
            response = self.session.get(self.api_url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                for job in data:
                    title = job.get("text", "")
                    title_lower = title.lower()
                    is_intern = any(t in title_lower for t in ["intern", "co-op", "coop", "internship"])
                    matches_specialty = self.matches_keywords(title, keywords)

                    if is_intern and matches_specialty:
                        # Parse date
                        posted_date = None
                        created_at = job.get("createdAt")
                        if created_at:
                            try:
                                posted_date = datetime.fromtimestamp(created_at / 1000)
                            except:
                                pass

                        categories = job.get("categories", {})
                        location = categories.get("location", "")

                        job_posting = JobPosting(
                            company=self.company_name,
                            title=title,
                            location=location,
                            url=job.get("hostedUrl", ""),
                            posted_date=posted_date,
                            job_id=job.get("id", ""),
                        )
                        jobs.append(job_posting)
            else:
                logger.debug(f"{self.company_name} Lever API returned {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching {self.company_name} jobs: {e}")

        return jobs


class SmartRecruitersScraper(BaseScraper):
    """Generic scraper for SmartRecruiters-based career sites."""

    def __init__(self, company_name: str, config: Dict, api_url: str):
        super().__init__(company_name, config)
        # Extract company slug from URL like https://api.smartrecruiters.com/v1/companies/biogen/postings
        if "smartrecruiters.com" in api_url:
            parts = api_url.split("/companies/")
            if len(parts) > 1:
                self.company_slug = parts[1].split("/")[0]
            else:
                self.company_slug = company_name.lower().replace(" ", "")
        else:
            self.company_slug = api_url
        self.api_url = f"https://api.smartrecruiters.com/v1/companies/{self.company_slug}/postings"

    def fetch_jobs(self, keywords: List[str], days_back: int = 7) -> List[JobPosting]:
        jobs = []

        try:
            time.sleep(0.3)
            params = {"limit": 100}
            response = self.session.get(self.api_url, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                for job in data.get("content", []):
                    title = job.get("name", "")
                    title_lower = title.lower()
                    is_intern = any(t in title_lower for t in ["intern", "co-op", "coop", "internship"])
                    matches_specialty = self.matches_keywords(title, keywords)

                    if is_intern and matches_specialty:
                        # Parse location
                        location_obj = job.get("location", {})
                        location = location_obj.get("city", "")
                        if location_obj.get("region"):
                            location += f", {location_obj.get('region')}"
                        if location_obj.get("country"):
                            location += f", {location_obj.get('country')}"

                        # Parse date
                        posted_date = None
                        date_str = job.get("releasedDate")
                        if date_str:
                            try:
                                posted_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                            except:
                                pass

                        job_posting = JobPosting(
                            company=self.company_name,
                            title=title,
                            location=location.strip(", "),
                            url=job.get("ref", f"https://jobs.smartrecruiters.com/{self.company_slug}/{job.get('id', '')}"),
                            posted_date=posted_date,
                            job_id=job.get("id", ""),
                        )
                        jobs.append(job_posting)
            else:
                logger.debug(f"{self.company_name} SmartRecruiters API returned {response.status_code}")
        except Exception as e:
            logger.debug(f"Error fetching {self.company_name} jobs: {e}")

        return jobs


class EightfoldScraper(BaseScraper):
    """Generic scraper for Eightfold AI-based career sites."""

    def __init__(self, company_name: str, config: Dict, api_url: str):
        super().__init__(company_name, config)
        self.api_url = api_url

    def fetch_jobs(self, keywords: List[str], days_back: int = 7) -> List[JobPosting]:
        jobs = []

        try:
            time.sleep(0.3)
            # Eightfold API uses POST with JSON payload
            payload = {
                "query": "intern",
                "limit": 100,
                "offset": 0,
            }
            self.session.headers.update({"Content-Type": "application/json"})
            response = self.session.post(self.api_url, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                for job in data.get("positions", data.get("jobs", [])):
                    title = job.get("name", job.get("title", ""))
                    title_lower = title.lower()
                    is_intern = any(t in title_lower for t in ["intern", "co-op", "coop", "internship"])
                    matches_specialty = self.matches_keywords(title, keywords)

                    if is_intern and matches_specialty:
                        job_posting = JobPosting(
                            company=self.company_name,
                            title=title,
                            location=job.get("location", ""),
                            url=job.get("url", job.get("apply_url", "")),
                            job_id=job.get("id", ""),
                        )
                        jobs.append(job_posting)
            else:
                logger.debug(f"{self.company_name} Eightfold API returned {response.status_code}")
        except Exception as e:
            logger.debug(f"Error fetching {self.company_name} jobs: {e}")

        return jobs


class TikTokScraper(BaseScraper):
    """Scraper for TikTok/ByteDance careers."""

    def fetch_jobs(self, keywords: List[str], days_back: int = 7) -> List[JobPosting]:
        jobs = []
        base_url = "https://careers.tiktok.com/api/v1/search/job/posts"

        params = {
            "keyword": "intern",
            "limit": 100,
            "offset": 0,
            "portal_type": 1,
        }

        try:
            response = self.session.get(base_url, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                for job in data.get("data", {}).get("job_post_list", []):
                    title = job.get("title", "")
                    title_lower = title.lower()
                    is_intern = any(t in title_lower for t in ["intern", "co-op", "coop"])
                    matches_specialty = self.matches_keywords(title, keywords)

                    if is_intern and matches_specialty:
                        job_id = job.get("id", "")
                        job_posting = JobPosting(
                            company=self.company_name,
                            title=title,
                            location=job.get("location", ""),
                            url=f"https://careers.tiktok.com/position/{job_id}",
                            job_id=str(job_id),
                        )
                        jobs.append(job_posting)
        except Exception as e:
            logger.error(f"Error fetching TikTok jobs: {e}")

        return jobs


class NetflixScraper(BaseScraper):
    """Scraper for Netflix careers."""

    def fetch_jobs(self, keywords: List[str], days_back: int = 7) -> List[JobPosting]:
        jobs = []
        base_url = "https://jobs.netflix.com/api/search"

        params = {
            "q": "intern",
            "page": 1,
        }

        try:
            response = self.session.get(base_url, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                for job in data.get("records", {}).get("postings", []):
                    title = job.get("text", "")
                    title_lower = title.lower()
                    is_intern = any(t in title_lower for t in ["intern", "co-op", "coop"])
                    matches_specialty = self.matches_keywords(title, keywords)

                    if is_intern and matches_specialty:
                        posted_date = None
                        date_str = job.get("posted_date")
                        if date_str:
                            try:
                                posted_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                            except:
                                pass

                        job_posting = JobPosting(
                            company=self.company_name,
                            title=title,
                            location=job.get("location", ""),
                            url=f"https://jobs.netflix.com/jobs/{job.get('external_id', '')}",
                            posted_date=posted_date,
                            job_id=job.get("external_id", ""),
                        )
                        jobs.append(job_posting)
        except Exception as e:
            logger.error(f"Error fetching Netflix jobs: {e}")

        return jobs


def get_scraper(company_key: str, company_config: Dict) -> Optional[BaseScraper]:
    """Factory function to get the appropriate scraper for a company."""
    # Direct scrapers for specific companies
    direct_scrapers = {
        "Alphabet": GoogleScraper,
        "Google": GoogleScraper,
        "Amazon": AmazonScraper,
        "Apple": AppleScraper,
        "Meta": MetaScraper,
        "Microsoft": MicrosoftScraper,
        "Nvidia": NvidiaScraper,
        "Tesla": TeslaScraper,
        "TikTok": TikTokScraper,
        "Netflix": NetflixScraper,
    }

    company_name = company_config.get("name", company_key)
    api_url = company_config.get("api_url", "")
    scraper_type = company_config.get("type", "").lower()

    # Check for direct scraper first
    if company_key in direct_scrapers:
        return direct_scrapers[company_key](company_name, company_config)

    # Check for scraper type in config
    if scraper_type == "workday" or "myworkdayjobs.com" in api_url.lower():
        return GenericWorkdayScraper(company_name, company_config, api_url)

    if scraper_type == "greenhouse" or "greenhouse.io" in api_url.lower():
        return GreenhouseScraper(company_name, company_config, api_url)

    if scraper_type == "lever" or "lever.co" in api_url.lower():
        return LeverScraper(company_name, company_config, api_url)

    if scraper_type == "smartrecruiters" or "smartrecruiters.com" in api_url.lower():
        return SmartRecruitersScraper(company_name, company_config, api_url)

    if scraper_type == "eightfold" or "eightfold.ai" in api_url.lower():
        return EightfoldScraper(company_name, company_config, api_url)

    # Log but don't warn for every company - some just don't have scrapers yet
    logger.debug(f"No scraper available for {company_key}")
    return None


@dataclass
class CompanySearchResult:
    """Tracks the result of searching a company."""
    company_name: str
    status: str  # "success", "no_matching_jobs", "api_error", "no_scraper"
    jobs_found: int = 0
    total_jobs_fetched: int = 0
    message: str = ""


def fetch_all_jobs(config: Dict) -> tuple:
    """
    Fetch jobs from all configured companies.

    Returns:
        tuple: (List[JobPosting], Dict[str, List[str]])
               - jobs: List of matching job postings
               - search_results: Dict with categories:
                   "success": companies that returned matching jobs
                   "no_matching_jobs": API worked but no matching intern/specialty jobs
                   "api_error": API returned error or failed
    """
    all_jobs = []
    search_results = {
        "success": [],
        "no_matching_jobs": [],
        "api_error": [],
    }
    days_back = config.get("days_lookback", 7)

    # Get keywords for filtering
    title_keywords = config.get("job_title_keywords", [])  # intern, co-op, etc.
    specialty_keywords = config.get("specialty_keywords", [])  # AI, ML, data science, etc.

    companies = config.get("companies", {})

    for company_key, company_config in companies.items():
        company_name = company_config.get("name", company_key)
        logger.info(f"Fetching jobs from {company_key}...")
        scraper = get_scraper(company_key, company_config)

        if scraper:
            try:
                # Pass specialty keywords to scraper - each scraper handles intern filtering internally
                jobs = scraper.fetch_jobs(specialty_keywords, days_back)
                total_fetched = len(jobs)

                # Jobs from scrapers should already be filtered for intern + specialty
                # Just do a final verification - be inclusive
                filtered_jobs = []
                for job in jobs:
                    title_lower = job.title.lower()
                    # Must be intern/co-op
                    is_intern = any(kw.lower() in title_lower for kw in title_keywords)
                    # Check for specialty match
                    matches_specialty = any(kw.lower() in title_lower for kw in specialty_keywords)
                    # Relevant technical terms
                    relevant_terms = ["research", "scientist", "engineer", "developer", "analyst",
                                      "software", "hardware", "systems", "platform"]
                    has_relevant_term = any(t in title_lower for t in relevant_terms)

                    if is_intern:
                        if matches_specialty or has_relevant_term:
                            filtered_jobs.append(job)

                all_jobs.extend(filtered_jobs)
                logger.info(f"  Found {len(filtered_jobs)} matching jobs from {company_key}")

                # Track result
                if len(filtered_jobs) > 0:
                    search_results["success"].append(company_name)
                else:
                    # API worked but no matching jobs
                    search_results["no_matching_jobs"].append(company_name)

                # Rate limiting
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error processing {company_key}: {e}")
                search_results["api_error"].append(company_name)
        else:
            # No scraper available for this company type
            search_results["api_error"].append(company_name)

    # Remove duplicates based on job_id and URL
    seen = set()
    unique_jobs = []
    for job in all_jobs:
        key = (job.company, job.job_id or job.url)
        if key not in seen:
            seen.add(key)
            unique_jobs.append(job)

    return unique_jobs, search_results
