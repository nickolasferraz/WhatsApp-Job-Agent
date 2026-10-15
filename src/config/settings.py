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

    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    serpapi_key: str = Field(default="", alias="SERPAPI_KEY")
    authentication_api_key: str = Field(default="", alias="AUTHENTICATION_API_KEY")
    evolution_api_url: str = Field(default="http://localhost:8082", alias="EVOLUTION_API_URL")
    evolution_api_version: str = Field(default="v2.2.3", alias="EVOLUTION_API_VERSION")

    whatsapp_instance_name: str = Field(default="", alias="WHATSAPP_INSTANCE_NAME")
    ia_version: str = Field(default="gemini-2.5-flash", alias="IA_VERSION")
    min_score_to_notify: int = Field(default=60, alias="MIN_SCORE_TO_NOTIFY")
    max_results_per_query: int = 10
    # Limite de vagas enviadas por execucao do pipeline
    max_notifications_per_run: int = Field(default=10, alias="MAX_NOTIFICATIONS_PER_RUN")
    # Numero de browsers paralelos no scraping (Fase 1)
    scrape_workers: int = Field(default=4, alias="SCRAPE_WORKERS")
    # Redis para armazenar vagas ja enviadas
    redis_url: str = Field(default="redis://localhost:6379/2", alias="REDIS_URL")
    redis_ttl_days: int = Field(default=30, alias="REDIS_TTL_DAYS")

    # Database Config
    DB_HOST: str = Field(default="localhost", alias="DB_HOST")
    DB_PORT: int = Field(default=5432, alias="DB_PORT")
    DB_USER: str = Field(default="postgres", alias="DB_USER")
    DB_PASSWORD: str = Field(default="postgres", alias="DB_PASSWORD")
    DB_NAME: str = Field(default="postgres", alias="DB_NAME")    

    # Sites usados nas queries de busca (SerpAPI)
    target_sites: list[str] = [
        "linkedin.com/jobs",
        "gupy.io",
        "catho.com.br",
        # Adicionado: Job Boards
        "lever.co",
        "indeed.com",
        "glassdoor.com",
        "wellfound.com",
        "remoteok.com",
        "weworkremotely.com",
        # Adicionado: Outsourcings
        "x-team.com",
        "cake.com",
        "bairesdev.com",
        "toptal.com",
        "revelo.com.br",
        # Adicionado: Big Techs (careers diretos)
        "careers.google.com",
        "metacareers.com",
        "jobs.apple.com",
        "amazon.jobs",
        "careers.microsoft.com",
        "jobs.netflix.com",
        "lifeatspotify.com",
        "uber.com/careers",
        # Adicionado: Comunidades e repositórios
        "news.ycombinator.com",       # Hacker News Who Is Hiring
        "github.com/remoteintech",    # Remote In Tech repo
    ]

    # Sites que usam scraping estatico (httpx) em vez de Playwright
    # Geralmente sites com renderizacao server-side sem muito JS
    static_sites: list[str] = [
        "catho.com.br",
        "infojobs.com.br",
        "vagas.com.br",
        # Adicionado
        "remoteok.com",
        "weworkremotely.com",
        "news.ycombinator.com",
        "wellfound.com",
        "revelo.com.br",
        "glassdoor.com",
    ]

    # Adicionado
    boolean_search_queries: list[str] = [
        # Lever — vagas escondidas não indexadas no LinkedIn
        'site:lever.co ({stack} OR {framework}) AND (Remote OR Latam OR "Latin America" OR Brazil)',

        # LinkedIn Jobs
        'site:linkedin.com/jobs ({stack} OR {framework}) AND (Remote) AND (Brazil OR Latam)',

        # LinkedIn Posts de recrutadores (não aba Jobs)
        'site:linkedin.com (hiring OR "we are hiring" OR "open position") AND ({stack}) AND (Remote OR Latam)',

        # Boards diversos + GitHub Jobs
        '({stack} OR {framework}) AND (Remote OR "Latin America") AND ("software engineer" OR developer)',

        # Hacker News Who Is Hiring (mês atual)
        'site:news.ycombinator.com "Who is hiring" "2026" {stack}',

        # Remote In Tech (GitHub repo)
        'site:github.com/remoteintech {stack} developer remote',

        # Recrutadores no LinkedIn direto
        '"Tech Recruiter" AND ({stack} OR "software engineer") AND (Brazil OR Latam OR Germany OR Netherlands)',
    ]

    # Adicionado
    github_remote_in_tech_api: str = "https://api.github.com/repos/remoteintech/remote-jobs/contents/company-profiles"
    github_remote_in_tech_readme: str = "https://github.com/remoteintech/remote-jobs/blob/main/README.md"

    # Configurações globais antigas removidas. 
    # Agora as keywords e o currículo são obtidos dinamicamente de cada usuário no Banco de Dados!
    
#isso evita que a classe Settings seja instanciada múltiplas vezes
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
