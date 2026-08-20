"""Garante que a raiz do repositório esteja em `sys.path`.

Necessário porque `streamlit run dashboard/app.py` coloca `dashboard/` (não
a raiz do repo) como primeiro item de `sys.path` — sem isso, `import
src...` falharia tanto localmente quanto no Streamlit Community Cloud.
Importado no topo de `app.py` e de cada página em `dashboard/pages/`
(não depende de nada do próprio projeto, só de `pathlib`/`sys`, para poder
ser importado antes de qualquer outra coisa).
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ_REPOSITORIO = Path(__file__).resolve().parent.parent

if str(RAIZ_REPOSITORIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPOSITORIO))
