from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from config.settings import settings

# Criar a string de conexão baseada nas configurações
SQLALCHEMY_DATABASE_URL = f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"

# O pool_pre_ping=True verifica se a conexão ainda está viva antes de usá-la
engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)

# Sessão do banco de dados
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para criar as classes de modelo
Base = declarative_base()

def get_db():
    """
    Função geradora para obter a sessão do banco de dados.
    Fecha a sessão automaticamente após o uso.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables():
    """
    Cria todas as tabelas no banco de dados que herdam do Base.
    Lembre-se de importar os seus modelos (ex: models.job) antes de chamar isso!
    """
    Base.metadata.create_all(bind=engine)