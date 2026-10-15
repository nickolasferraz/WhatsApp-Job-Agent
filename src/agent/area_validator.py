# agent/area_validator.py
import re

# Padrões comuns de cargos e áreas de TI, tolerante a variações
_TI_KEYWORDS = re.compile(
    r"\b(software|developer|desenvolvedor|programmer|programador|dev|engineer|engenheiro|swe|ti|it|"
    r"data|dados|analytics|machine learning|ml|ai|ia|artificial intelligence|inteligencia artificial|"
    r"cloud|devops|sre|sysadmin|network|rede|security|seguranca|cybersecurity|"
    r"qa|tester|quality assurance|automation|automação|"
    r"frontend|front-end|backend|back-end|fullstack|full-stack|mobile|ios|android|web|"
    r"product manager|pm|product owner|po|scrum|agile|ux|ui|design|designer|arquitet|architect|"
    r"tech lead|cto|infraestrutura|infra)\b",
    re.IGNORECASE
)

def is_ti_user(user) -> bool:
    """
    Verifica se o usuário é da área de TI baseado nos seus keyword_roles.
    É case-insensitive e tolerante a variações.
    """
    if not user or not user.keyword_roles:
        return False
        
    for role in user.keyword_roles:
        if _TI_KEYWORDS.search(role):
            return True
            
    return False
