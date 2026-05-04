from pydantic import BaseModel

class ResumeProfile(BaseModel):
    name: str = ""
    target_roles: list[str] = []
    skills: list[str] = []
    languages: list[str] = []
    seniority: str = "junior"
    locations_accepted: list[str] = []
    work_modes_accepted: list[str] = []
    summary: str = ""
    raw_text: str = ""