# tests/test_sectors_and_multi_resume.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from config.sectors import resolve_sector, keyword_sectors, SECTORS
from agent.sector_filter import is_sector_acceptable, company_matches
from agent.query_builder import BooleanQueryBuilder
from agent.seen_store import _job_fingerprint

def test_sector_resolution():
    assert resolve_sector("automotivo") == "automotivo"
    assert resolve_sector("Automotivo") == "automotivo"
    assert resolve_sector("montadora") == "automotivo"
    assert resolve_sector("logistica") == "logistica"
    assert resolve_sector("supply chain") == "logistica"
    assert resolve_sector("tecnologia") == "tecnologia"
    print("✅ test_sector_resolution passou!")

def test_sector_filter_scenarios():
    job_volks = {
        "title": "Engenheiro de Produto",
        "company": "Volkswagen do Brasil",
        "industries": ["automotivo"],
        "industry_description": "Fabricante de veículos automotores"
    }

    # 1. Filtro automotivo aceita
    ok, reason = is_sector_acceptable(job_volks, target_sectors=["automotivo"])
    assert ok, f"Falhou: {reason}"

    # 2. Filtro apenas logística rejeita
    ok, reason = is_sector_acceptable(job_volks, target_sectors=["logistica"])
    assert not ok, f"Deveria rejeitar: {reason}"

    # 3. Empresa excluída rejeita mesmo que o setor seja compatível
    ok, reason = is_sector_acceptable(
        job_volks,
        target_sectors=["automotivo"],
        excluded_companies=["Volkswagen"]
    )
    assert not ok and "excluida" in reason, f"Deveria rejeitar por empresa excluída: {reason}"

    # 4. Empresa-alvo aceita independente do setor
    job_desconhecido = {
        "title": "Analista",
        "company": "Bosch Rexroth",
        "industries": [],
        "industry_description": ""
    }
    ok, reason = is_sector_acceptable(
        job_desconhecido,
        target_sectors=["automotivo"],
        target_companies=["Bosch"]
    )
    assert ok and "empresa-alvo" in reason, f"Deveria aceitar por empresa-alvo: {reason}"

    print("✅ test_sector_filter_scenarios passou!")

def test_query_builder():
    builder = BooleanQueryBuilder(
        keyword_roles=["Engenheiro de Manutenção"],
        keyword_locations=["Campinas", "São Paulo"],
        target_sectors=["automotivo"],
        target_companies=["Toyota", "Honda"]
    )
    query = builder.build("linkedin.com/jobs")
    assert "site:linkedin.com/jobs" in query
    assert '"Engenheiro de Manutenção"' in query
    assert '"Toyota" OR "Honda"' in query
    assert not " + " in query
    print("✅ test_query_builder passou!")

def test_fingerprint():
    fp1 = _job_fingerprint("Engenheiro Automotivo - São Paulo/SP", "Volkswagen")
    fp2 = _job_fingerprint("Engenheiro Automotivo", "Volkswagen")
    assert fp1 == fp2, "Deveria normalizar títulos e cidades"
    print("✅ test_fingerprint passou!")

if __name__ == "__main__":
    test_sector_resolution()
    test_sector_filter_scenarios()
    test_query_builder()
    test_fingerprint()
    print("\n🎉 TODOS OS TESTES PASSARAM COM SUCESSO!")
