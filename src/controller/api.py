import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi import FastAPI, Depends, HTTPException, File, UploadFile, Form, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import uvicorn
import uuid

from config.database import get_db, create_tables
from config.sectors import SECTORS
from models.job import User, Resume, UserOut, ResumeOut

# Cria as tabelas no banco de dados se ainda não existirem
create_tables()

@asynccontextmanager
async def lifespan(app: FastAPI):
    from main import job as pipeline_job
    scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
    scheduler.add_job(pipeline_job, CronTrigger(
        day_of_week="mon-fri",
        hour="8,10,13,16",
        minute="0"
    ))
    scheduler.start()
    print("🤖 Robô agendador iniciado em background!")
    
    # Executa a pipeline logo ao iniciar a API para checar novas vagas
    scheduler.add_job(pipeline_job)
    
    yield
    
    print("🛑 Encerrando agendador...")
    scheduler.shutdown()

app = FastAPI(
    title="WhatsApp Job Agent API",
    description="API para gerenciar usuários, múltiplos perfis de currículo e filtros de setor",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def serve_home():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    index_path = os.path.join(root_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Arquivo index.html não encontrado na raiz do projeto."}

@app.get("/sectors")
def list_available_sectors():
    """
    Retorna a lista de setores disponíveis na taxonomia oficial do sistema.
    """
    return [
        {
            "key": s.key,
            "label": s.label,
            "search_terms": list(s.search_terms),
        }
        for s in SECTORS.values()
    ]

@app.post("/users/upload/", status_code=201)
async def upload_resume(
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    name: str = Form(...),
    phone: str = Form(""),
    label: str = Form("Currículo Principal"),
    keyword_roles: str = Form(""),
    keyword_locations: str = Form(""),
    keyword_levels: str = Form(""),
    target_sectors: str = Form(""),
    target_companies: str = Form(""),
    excluded_companies: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Cadastra um novo perfil de busca com currículo.
    Se o e-mail já existir, adiciona o novo currículo como perfil adicional do usuário!
    """
    email_clean = email.strip().lower()
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Arquivo PDF vazio ou inválido.")

    roles = [r.strip() for r in keyword_roles.split(",") if r.strip()] if keyword_roles else []
    locations = [l.strip() for l in keyword_locations.split(",") if l.strip()] if keyword_locations else []
    levels = [lvl.strip() for lvl in keyword_levels.split(",") if lvl.strip()] if keyword_levels else []
    sectors = [s.strip().lower() for s in target_sectors.split(",") if s.strip()] if target_sectors else []
    target_comps = [c.strip() for c in target_companies.split(",") if c.strip()] if target_companies else []
    excluded_comps = [ec.strip() for ec in excluded_companies.split(",") if ec.strip()] if excluded_companies else []

    # Procura usuário existente ou cria novo
    db_user = db.query(User).filter(User.email == email_clean).first()
    if not db_user:
        db_user = User(
            name=name.strip(),
            email=email_clean,
            phone=phone.strip(),
            groups=[],
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
    else:
        # Atualiza nome e telefone se fornecidos
        if name.strip():
            db_user.name = name.strip()
        if phone.strip():
            db_user.phone = phone.strip()
        db.add(db_user)
        db.commit()

    # Cria o novo perfil de currículo (Resume)
    resume = Resume(
        user_id=db_user.id,
        label=label.strip() or f"Currículo {len(db_user.resumes) + 1}",
        filename=file.filename or "curriculo.pdf",
        resume_pdf=pdf_bytes,
        keyword_roles=roles,
        keyword_locations=locations,
        keyword_levels=levels,
        target_sectors=sectors,
        target_companies=target_comps,
        excluded_companies=excluded_comps,
        is_active=True,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    # Dispara busca de vagas em background para o usuário
    from main import run_pipeline_for_user_by_id
    background_tasks.add_task(run_pipeline_for_user_by_id, db_user.id)

    return {
        "message": f"Perfil '{resume.label}' cadastrado com sucesso para {db_user.name}!",
        "user_id": db_user.id,
        "resume_id": resume.id,
        "is_new_user": len(db_user.resumes) == 1
    }

@app.get("/users/", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db)):
    """
    Lista todos os usuários e seus respectivos perfis de currículos cadastrados (sem expor o PDF).
    """
    users = db.query(User).all()
    return users

@app.get("/users/{email}/resumes", response_model=List[ResumeOut])
def get_user_resumes(email: str, db: Session = Depends(get_db)):
    """
    Lista todos os currículos de um usuário específico por e-mail.
    """
    user = db.query(User).filter(User.email == email.strip().lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return user.resumes

@app.delete("/resumes/{resume_id}")
def delete_resume(resume_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Remove um perfil de currículo.
    """
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Currículo não encontrado.")
    db.delete(resume)
    db.commit()
    return {"message": "Perfil de currículo excluído com sucesso."}

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
