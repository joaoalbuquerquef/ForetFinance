# ForêtFinance

🇫🇷 [Français](README.md) · 🇧🇷 **Português**

**Diagnóstico de financiamentos florestais para proprietários privados na França.** Com poucas perguntas, o aplicativo
identifica os auxílios para os quais uma parcela é elegível, propõe a combinação mais vantajosa, estima os valores e o
potencial de carbono e gera uma recomendação personalizada com o Claude.

![Python](https://img.shields.io/badge/Python-3-informational?style=flat-square)
![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey?style=flat-square)
![Folium](https://img.shields.io/badge/Folium-0.16+-77B829?style=flat-square)

---

## Funcionalidades

- **Formulário de diagnóstico**: tempo de propriedade, área, estado do povoamento, tipo de proprietário, região, terreno
  sem floresta há 10 anos, zona Natura 2000.
- **Geolocalização da parcela**: a partir de um endereço (API Adresse do data.gouv.fr) ou de coordenadas `lat, lon`, o
  aplicativo detecta a região e verifica se o ponto está em zona Natura 2000 (serviço WFS do INPN).
- **Motor de elegibilidade**: regras declarativas em `data/financements.json` (critérios obrigatórios e restritivos,
  com alternativas) aplicadas a 7 mecanismos:

  | Mecanismo | Tipo |
  |---|---|
  | Label Bas Carbone — Boisement (florestamento) | Créditos de carbono |
  | Label Bas Carbone — Reconstitution (reconstituição) | Créditos de carbono |
  | Label Bas Carbone — Conversion de taillis (conversão de talhadia) | Créditos de carbono |
  | France Nation Verte — Renouvellement forestier | Subvenção |
  | FEADER — Aide au reboisement | Subvenção |
  | DEFI Travaux — Crédit d'impôt forestier | Benefício fiscal |
  | Contrats Natura 2000 | Contrato com o Estado |

- **Combinação ótima**: busca o maior conjunto de mecanismos acumuláveis (ou a combinação recomendada para povoamentos
  sinistrados / em declínio mantidos há 30 anos ou mais), com o financiamento direto estimado (mín. – máx.).
- **Estimador de carbono**: sequestro anual e em 30 anos, e receita potencial segundo uma faixa de preço do crédito.
- **Recomendação personalizada por IA**: três parágrafos escritos pelo Claude (API da Anthropic) no papel de um consultor
  florestal: por que a parcela é elegível, qual combinação escolher e três ações prioritárias.
- **Mapa das zonas Natura 2000** (`/map`): mapa em Folium com sítios florestais representativos.
- **Formulário de contato**: os pedidos são gravados em `data/contacts.json`.

A interface do aplicativo é em francês.

## Instalação

```bash
git clone https://github.com/joaoalbuquerquef/ForetFinance.git
cd ForetFinance
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Crie um arquivo `.env` na raiz com a sua chave de API:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Sem a chave, o diagnóstico funciona normalmente; só a recomendação personalizada mostra uma mensagem de indisponibilidade.

## Como rodar

```bash
python app.py
```

O aplicativo sobe em `http://localhost:5000` (ou na porta definida pela variável `PORT`). O `Procfile` permite o deploy
no Heroku, Railway ou Render.

## Rotas

| Rota | Método | Função |
|---|---|---|
| `/` | GET | Formulário de diagnóstico |
| `/diagnose` | POST | Geolocalização, elegibilidade, combinação ótima, recomendação por IA |
| `/contact` | POST | Grava um pedido de contato |
| `/map` | GET | Mapa das zonas Natura 2000 |

## Estrutura

```
app.py                  Rotas Flask, chamada à API da Anthropic, mapa Folium
matching.py             Motor de elegibilidade, estimativa de valores, combinação ótima, carbono
geo.py                  Geocodificação (API Adresse) e teste Natura 2000 (WFS do INPN)
data/financements.json  Base de regras: mecanismos, acúmulos, estimador de carbono, campos do formulário
data/contacts.json      Pedidos de contato recebidos
templates/              index.html, result.html, contact_confirmation.html
static/style.css
```

## Atualizar as regras

Toda a lógica de negócio está em `data/financements.json`: para incluir um mecanismo ou mudar um critério ou uma taxa,
basta editar esse arquivo, sem mexer no código. Cada mecanismo declara seus `criteres_eligibilite` (`obligatoires`,
`restrictifs`), seu `montant` (`variable`, `pourcentage`, `pourcentage_regional`, `credit_impot`) e a lista de mecanismos
com os quais é acumulável (`cumulable_avec`).

## Limitações

- Os valores são **estimativas indicativas** (custo de referência de 9.000 €/ha em obras, 5 tCO₂/ha/ano para um
  povoamento misto) e não substituem a análise de um pedido pelo CNPF ou pela DDT.
- Os campos que não estão no formulário (espécies, plano de manejo etc.) são considerados favoráveis.
- Fontes das regras: CNPF, Ministério da Transição Ecológica, IGN (abril de 2026).
