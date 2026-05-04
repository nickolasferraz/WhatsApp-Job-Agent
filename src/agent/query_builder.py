import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import settings
from typing import List

class BooleanQueryBuilder:

    def _or_group(self, terms: List[str]) -> str:
        quoted=[f'"{t}"' for t in terms]
        return f"({' OR '.join(quoted)})"


    def build(self,site:str) -> str:
        groups=[
            self._or_group(settings.keyword_roles),
            self._or_group(settings.keyword_locations),
            self._or_group(settings.keyword_levels),
            self._or_group([site])
        ]

        return f" site:{site} + {' AND '.join(groups)}" 
        # Logica de Boolean search

    def all_queries(self) -> list[dict]:
        return [
            {"site": site, "query": self.build(site)}
            for site in settings.target_sites
        ]
if __name__ == "__main__":
    print(BooleanQueryBuilder().all_queries())
    