import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import settings
from config.sectors import SECTORS, resolve_sector
from typing import List, Optional

class BooleanQueryBuilder:
    def __init__(
        self,
        keyword_roles: Optional[List[str]] = None,
        keyword_locations: Optional[List[str]] = None,
        keyword_levels: Optional[List[str]] = None,
        target_sectors: Optional[List[str]] = None,
        target_companies: Optional[List[str]] = None,
    ):
        self.keyword_roles = [r.strip() for r in (keyword_roles or []) if r and r.strip()]
        self.keyword_locations = [l.strip() for l in (keyword_locations or []) if l and l.strip()]
        self.keyword_levels = [lvl.strip() for lvl in (keyword_levels or []) if lvl and lvl.strip()]
        self.target_sectors = [s.strip() for s in (target_sectors or []) if s and s.strip()]
        self.target_companies = [c.strip() for c in (target_companies or []) if c and c.strip()]

    def _or_group(self, terms: List[str]) -> str:
        if not terms:
            return ""
        # Remove aspas se já vierem com aspas
        cleaned = [t.strip('"\'') for t in terms if t.strip()]
        if not cleaned:
            return ""
        if len(cleaned) == 1:
            return f'"{cleaned[0]}"'
        quoted = [f'"{t}"' for t in cleaned]
        return f"({' OR '.join(quoted)})"

    def _sector_search_terms(self) -> List[str]:
        terms = []
        for sec in self.target_sectors:
            key = resolve_sector(sec)
            if key and key in SECTORS:
                terms.extend(SECTORS[key].search_terms[:3])
            else:
                terms.append(sec)
        return list(dict.fromkeys(terms))

    def build(self, site: str) -> str:
        groups = []

        if self.keyword_roles:
            groups.append(self._or_group(self.keyword_roles))

        # Se o usuário definiu empresas-alvo, inclui no filtro de busca
        if self.target_companies:
            groups.append(self._or_group(self.target_companies[:6]))
        elif self.target_sectors:
            sector_terms = self._sector_search_terms()
            if sector_terms:
                groups.append(self._or_group(sector_terms[:5]))

        if self.keyword_locations:
            groups.append(self._or_group(self.keyword_locations))

        if self.keyword_levels:
            groups.append(self._or_group(self.keyword_levels))

        query_parts = [f"site:{site}"]
        for g in groups:
            if g:
                query_parts.append(g)

        return " ".join(query_parts)

    def all_queries(self) -> list[dict]:
        return [
            {"site": site, "query": self.build(site)}
            for site in settings.target_sites
        ]

if __name__ == "__main__":
    builder = BooleanQueryBuilder(
        keyword_roles=["Engenheiro Mecânico", "Analista de Processos"],
        keyword_locations=["São Paulo", "ABC"],
        target_sectors=["automotivo"],
        target_companies=["Volkswagen", "Bosch"]
    )
    for q in builder.all_queries()[:3]:
        print(q)