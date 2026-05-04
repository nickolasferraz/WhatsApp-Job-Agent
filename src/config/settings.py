from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache

class Settings(BaseSettings):

    # Configuração do arquivo .env para leitura do arquivo de configuração
    # A função extra="ignore" faz com que o arquivo de configuração não seja lido
    # A função env_file_encoding="utf-8" faz com que o arquivo de configuração seja lido em utf-8
    # A função env_file=".env" faz com que o arquivo de configuração seja lido
    model_config= SettingsConfigDict(
        env_file= ".env",
        env_file_encoding="utf-8",
        extra="ignore", 
    )

    # Chaves da API que ja faz o Alias e o Cast dos arquivos .env para a classe Settings
    # o Alias é usado para que o nome da variável no arquivo .env seja diferente do nome da variável na classe Settings
    # o Cast é usado para que o tipo da variável no arquivo .env seja diferente do tipo da variável na classe Settings
    # O pydantic faz o cast automático das variáveis do arquivo .env para a classe Settings
    # O Field() faz o cast automático das variáveis do arquivo .env para a classe Settings

    gemini_api_key: str = Field(alias="GEMINI_API_KEY")
    serpapi_key: str = Field(alias="SERPAPI_KEY")
    authentication_api_key: str = Field(alias="AUTHENTICATION_API_KEY")
    evolution_api_url: str = Field(alias="EVOLUTION_API_URL")
    evolution_api_version: str = Field(alias="EVOLUTION_API_VERSION")
    whatsapp_target: str = Field(alias="WHATSAPP_TARGET")         # ← era whatsapp_group_jid no send
    whatsapp_instance_name: str = Field(alias="WHATSAPP_INSTANCE_NAME")  # ← era evolution_api_instance no send
    ia_version: str = Field(alias="IA_VERSION")
    min_score_to_notify: int = Field(default=60, alias="MIN_SCORE_TO_NOTIFY")
    max_results_per_query: int = 10
    # Limite de vagas enviadas por execucao do pipeline
    max_notifications_per_run: int = Field(default=10, alias="MAX_NOTIFICATIONS_PER_RUN")
    # Numero de browsers paralelos no scraping (Fase 1)
    scrape_workers: int = Field(default=4, alias="SCRAPE_WORKERS")
    # Redis para armazenar vagas ja enviadas
    redis_url: str = Field(default="redis://localhost:6379/2", alias="REDIS_URL")
    redis_ttl_days: int = Field(default=30, alias="REDIS_TTL_DAYS")

    # Sites usados nas queries de busca (SerpAPI)
    target_sites: list[str] = [
        "linkedin.com/jobs",
        "gupy.io",
        "catho.com.br",
    ]

    # Sites que usam scraping estatico (httpx) em vez de Playwright
    # Geralmente sites com renderizacao server-side sem muito JS
    static_sites: list[str] = [
        "catho.com.br",
        "infojobs.com.br",
        "vagas.com.br",
    ]

    # Grupos de keywords (booleanas)
    keyword_roles: list[str] = [
        "Supply chain", "Logistica",
        "Analista de logistica", "Assistente de logistica"
    ]
    keyword_locations: list[str] = [
        "São Paulo", "LATAM", "Brazil", "Remote"
    ]
    keyword_levels: list[str] = [
        "Junior", "Assistente", "Trainee","Estagiário"
    ]

    resume_path: str = "src/config/resume.pdf"
    
#isso evita que a classe Settings seja instanciada múltiplas vezes
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
