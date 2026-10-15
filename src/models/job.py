from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID
import uuid
from sqlalchemy import Column, String, LargeBinary, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from config.database import Base


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
    contract_type: Optional[str] = None
    seniority: Optional[str] = None
    salary_range: Optional[str] = None
    description: str = ""
    requirements: list[str] = []
    nice_to_have: list[str] = []
    languages: list[str] = []
    industries: list[str] = []
    industry_description: Optional[str] = None
    contact: Optional[JobContact] = None
    source_site: str = ""
    scraped_at: datetime = Field(default_factory=datetime.now)


class JobMatch(BaseModel):
    job: JobPosting
    score: int = 0
    probability_label: str = ""
    strengths: list[str] = []
    gaps: list[str] = []
    llm_summary: str = ""
    sent_to_whatsapp: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# ORM
# ──────────────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    phone = Column(String(50))
    groups = Column(ARRAY(String))

    # LEGADO: antes de existir a tabela `resumes`, o currículo e as keywords
    # ficavam no próprio usuário. Mantidos apenas para a migração automática
    # (ver main.migrate_legacy_resume). Novos cadastros não usam estes campos.
    resume = Column(LargeBinary)
    keyword_roles = Column(ARRAY(String))
    keyword_locations = Column(ARRAY(String))
    keyword_levels = Column(ARRAY(String))

    resumes = relationship(
        "Resume",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Resume.created_at",
    )


class Resume(Base):
    """
    Perfil de busca: um currículo + as preferências de busca associadas a ele.
    Um usuário pode ter vários (ex.: CV de Engenharia -> setor automotivo;
    CV de Analista -> setor de logística).
    """
    __tablename__ = "resumes"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    label = Column(String(120), nullable=False, default="Currículo")
    filename = Column(String(255))
    resume_pdf = Column(LargeBinary, nullable=False)
    # Perfil extraído pelo LLM (cache: o PDF só é parseado uma vez)
    parsed_profile = Column(JSONB)

    keyword_roles = Column(ARRAY(String), default=lambda: [])
    keyword_locations = Column(ARRAY(String), default=lambda: [])
    keyword_levels = Column(ARRAY(String), default=lambda: [])

    # Direcionamento por setor/empresa (filtro rígido)
    target_sectors = Column(ARRAY(String), default=lambda: [])
    target_companies = Column(ARRAY(String), default=lambda: [])
    excluded_companies = Column(ARRAY(String), default=lambda: [])

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="resumes")


# ──────────────────────────────────────────────────────────────────────────────
# Schemas da API (nunca expõem os bytes do PDF)
# ──────────────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None


class ResumeOut(BaseModel):
    id: UUID
    label: str
    filename: Optional[str] = None
    keyword_roles: list[str] = []
    keyword_locations: list[str] = []
    keyword_levels: list[str] = []
    target_sectors: list[str] = []
    target_companies: list[str] = []
    excluded_companies: list[str] = []
    is_active: bool = True
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: UUID
    name: str
    email: str
    phone: Optional[str] = None
    resumes: list[ResumeOut] = []

    model_config = {"from_attributes": True}