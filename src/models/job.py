from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class JobContact(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None

class JobPosting(BaseModel):
    id: str
    url: str
    title: str = ""
    company: str = ""
    location: Optional[str] = None
    work_mode: Optional[str] = None
    seniority: Optional[str] = None
    salary_range: Optional[str] = None
    description: str = ""
    requirements: list[str] = []
    nice_to_have: list[str] = []
    languages: list[str] = []
    contact: Optional[JobContact] = None
    source_site: str = ""
    scraped_at: datetime = datetime.now()


class JobMatch(BaseModel):
    job: JobPosting
    score: int = 0
    probability_label: str = ""
    strengths: list[str] = []
    gaps: list[str] = []
    llm_summary: str = ""
    sent_to_whatsapp: bool = False