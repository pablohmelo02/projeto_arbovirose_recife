"""Teste do dashboard em navegador real (Selenium + Chrome headless).

Uso:
    python scripts/testar_dashboard_navegador.py [--url http://localhost:8511] [--largura 1440]

Não é um teste unitário e **não** faz parte de `pytest` (depende de
navegador instalado e de uma instância do Streamlit no ar). É o
procedimento de verificação manual automatizado exigido antes de publicar:
percorre todas as páginas, interage com filtros, e falha se qualquer página
exibir exceção do Streamlit, *stack trace* ou ficar sem conteúdo.

`selenium` é dependência **apenas deste script** e não está em
`requirements.txt` — instale sob demanda com `pip install selenium`.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except ImportError:  # pragma: no cover - script opcional
    print("selenium não instalado. Rode: pip install selenium")
    sys.exit(2)

RAIZ = Path(__file__).resolve().parent.parent

PAGINAS = [
    "Início",
    "Situação epidemiológica",
    "Mapa territorial",
    "Evolução histórica",
    "Bairros prioritários",
    "Priorização experimental",
    "Clima",
    "Clima × Dengue",
    "Qualidade e limitações",
]

#: Marcadores de falha que nunca devem aparecer numa página pública.
MARCADORES_DE_FALHA = (
    "Traceback (most recent call last)",
    "StreamlitAPIException",
    "KeyError:",
    "AttributeError:",
    "TypeError:",
    "ValueError:",
    "IndexError:",
    "ModuleNotFoundError",
)

LARGURAS = {"desktop": (1440, 960), "tablet": (834, 1112), "mobile": (390, 844)}


def criar_navegador(largura: int, altura: int):
    opcoes = Options()
    opcoes.add_argument("--headless=new")
    opcoes.add_argument("--no-sandbox")
    opcoes.add_argument("--disable-dev-shm-usage")
    opcoes.add_argument(f"--window-size={largura},{altura}")
    return webdriver.Chrome(options=opcoes)


def esperar_render(navegador, segundos: float = 30.0) -> None:
    """Espera o app parar de mostrar o indicador de execução."""
    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        rodando = navegador.find_elements(By.CSS_SELECTOR, '[data-testid="stStatusWidget"]')
        if not rodando:
            time.sleep(0.6)
            return
        time.sleep(0.5)


def analisar_pagina(navegador, nome: str) -> dict:
    corpo = navegador.find_element(By.TAG_NAME, "body").text
    erros_st = navegador.find_elements(By.CSS_SELECTOR, '[data-testid="stException"]')
    alertas = navegador.find_elements(By.CSS_SELECTOR, '[data-testid="stAlert"]')
    graficos = navegador.find_elements(By.CSS_SELECTOR, ".js-plotly-plot")
    tabelas = navegador.find_elements(By.CSS_SELECTOR, '[data-testid="stDataFrame"]')
    marcadores = [m for m in MARCADORES_DE_FALHA if m in corpo]
    textos_alerta = [a.text.strip()[:160] for a in alertas]
    # A mensagem da fronteira de erro da UI: presente = alguma seção caiu.
    secoes_degradadas = [t for t in textos_alerta if "Não foi possível carregar esta análise" in t]

    largura_documento = navegador.execute_script("return document.documentElement.scrollWidth")
    largura_janela = navegador.execute_script("return window.innerWidth")

    return {
        "pagina": nome,
        "caracteres_texto": len(corpo),
        "excecoes_streamlit": len(erros_st),
        "alertas": len(alertas),
        "graficos_plotly": len(graficos),
        "tabelas": len(tabelas),
        "marcadores_de_falha": marcadores,
        "textos_alerta": textos_alerta,
        "secoes_degradadas": secoes_degradadas,
        "overflow_horizontal": bool(largura_documento > largura_janela + 2),
        "ok": not erros_st and not marcadores and not secoes_degradadas and len(corpo) > 400,
    }


def medir_carregamento(navegador) -> dict:
    """Tempos do Navigation Timing do próprio navegador — medição real, não
    estimativa (§51: o painel precisa continuar rápido)."""
    return navegador.execute_script(
        "const t = performance.getEntriesByType('navigation')[0];"
        "return t ? {dom_content_loaded_ms: Math.round(t.domContentLoadedEventEnd),"
        " load_ms: Math.round(t.loadEventEnd), transferido_kb: Math.round((t.transferSize||0)/1024)} : {};"
    )


def navegar_para(navegador, nome: str) -> bool:
    """Clica no item de navegação cujo texto corresponde a `nome`."""
    # O texto do link inclui o nome do ícone Material (ex.: "home" + quebra
    # de linha + "Início"), então a comparação usa a ÚLTIMA linha do texto.
    seletor = 'section[data-testid="stSidebar"] a'
    for link in navegador.find_elements(By.CSS_SELECTOR, seletor):
        linhas = [t.strip() for t in link.text.splitlines() if t.strip()]
        if linhas and linhas[-1] == nome:
            navegador.execute_script("arguments[0].click();", link)
            esperar_render(navegador)
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Testa o dashboard em navegador real.")
    parser.add_argument("--url", default="http://localhost:8511")
    parser.add_argument("--perfil", choices=list(LARGURAS), default="desktop")
    parser.add_argument("--todos-os-perfis", action="store_true")
    args = parser.parse_args()

    perfis = list(LARGURAS) if args.todos_os_perfis else [args.perfil]
    relatorio: dict[str, list[dict]] = {}
    falhas = 0

    for perfil in perfis:
        largura, altura = LARGURAS[perfil]
        print(f"\n=== perfil {perfil} ({largura}x{altura}) ===")
        try:
            navegador = criar_navegador(largura, altura)
        except WebDriverException as exc:
            print(f"Não foi possível iniciar o Chrome: {exc}")
            return 2

        resultados = []
        carregamento_inicial: dict = {}
        try:
            navegador.get(args.url)
            WebDriverWait(navegador, 60).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'section[data-testid="stSidebar"]'))
            )
            esperar_render(navegador, 60)

            carregamento_inicial = medir_carregamento(navegador)
            print(
                f"  carregamento inicial: DOM {carregamento_inicial.get('dom_content_loaded_ms')} ms · "
                f"load {carregamento_inicial.get('load_ms')} ms · "
                f"{carregamento_inicial.get('transferido_kb')} KB"
            )

            for nome in PAGINAS:
                inicio_navegacao = time.monotonic()
                if not navegar_para(navegador, nome):
                    print(f"  FALHA  {nome}: link de navegação não encontrado")
                    resultados.append({"pagina": nome, "ok": False, "erro": "link não encontrado"})
                    falhas += 1
                    continue
                resultado = analisar_pagina(navegador, nome)
                resultado["tempo_troca_de_pagina_s"] = round(time.monotonic() - inicio_navegacao, 2)
                resultados.append(resultado)
                marca = "ok    " if resultado["ok"] else "FALHA "
                print(
                    f"  {marca} {nome:<32} texto={resultado['caracteres_texto']:>6} "
                    f"graficos={resultado['graficos_plotly']} tabelas={resultado['tabelas']} "
                    f"alertas={resultado['alertas']} overflow={resultado['overflow_horizontal']} "
                    f"tempo={resultado['tempo_troca_de_pagina_s']}s"
                )
                if resultado["marcadores_de_falha"]:
                    print(f"         marcadores: {resultado['marcadores_de_falha']}")
                if resultado["secoes_degradadas"]:
                    print(f"         secoes degradadas: {len(resultado['secoes_degradadas'])}")
                if not resultado["ok"]:
                    falhas += 1
        except (TimeoutException, WebDriverException) as exc:
            print(f"  erro de navegação: {exc}")
            falhas += 1
        finally:
            navegador.quit()
        relatorio[perfil] = {
            "carregamento_inicial": carregamento_inicial,
            "paginas": resultados,
        }

    destino = RAIZ / "reports" / "product" / "browser_test_result.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRelatório salvo em {destino}")
    print(f"{'FALHOU' if falhas else 'PASSOU'} — {falhas} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
