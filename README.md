# Sistema Backtest

Dashboard Streamlit per backtest betting con **CCS** (Controlled Compounding in €), motore **tier** (T1–T4), ottimizzazione stake e combinazioni pattern.

Strategie: **HT**, **Over 1.5**, **Over 2.5**, **0 SH**, **1 SH**, **2 SH**, **Combined**, **Compound**, **FootyStats**, **Daily trades**.

## Requisiti

- Python 3.10 o superiore
- Streamlit ≥ 1.33

## Avvio locale

```bash
git clone https://github.com/andreapagliaro88-glitch/Backtest.git
cd Backtest

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Apri il browser su `http://localhost:8501`.

> **Nota:** `main.py` è uno script da terminale (export CSV/grafici). L'interfaccia web è `app.py`.

## Struttura dati

I file Excel (`.xlsx`) vanno nelle cartelle sotto `data/`:

| Cartella | Strategia |
|----------|-----------|
| `data/ht/` | Half Time |
| `data/over15/` | Over 1.5 |
| `data/over25/` | Over 2.5 |
| `data/sh0/` | 0 Second Half |
| `data/sh1/` | 1 Second Half |
| `data/sh2/` | 2 Second Half |
| `data/footystats/` | CSV FootyStats (analisi leghe) |
| `data/daily_trades/` | Journal operativo |

Dopo aver aggiunto o sostituito file, usa il pulsante **Aggiorna dati** in app per ricaricare la cache.

## Flusso tier (HT, O15, O25, SH)

1. **Ottimizza tier** — assegna pattern a T3 / T4 / esclusi  
2. **Simula stake** — ottimizza stake T1–T4 (mantiene i pattern del passo 1)  
3. **Combinazioni pattern** — scegli quali pattern includere nel portafoglio  

## Deploy Streamlit Cloud

1. Vai su [share.streamlit.io](https://share.streamlit.io) e accedi con GitHub  
2. **New app** → repository `andreapagliaro88-glitch/Backtest`  
3. **Main file path:** `app.py`  
4. **Branch:** `main`  
5. Nessun secret obbligatorio  
6. Python: `runtime.txt` (`python-3.11`)  

Dopo il deploy: i file Excel sono già nel repo sotto `data/`. Per aggiornarli in cloud, fai commit/push o carica dalla tab **Manuale** / **Aggiorna dati**.

## Configurazione

- Bankroll iniziale e regole CCS: `compound_config.py`
- Tema UI scuro: `.streamlit/config.toml`

## Test

```bash
pip install pytest
pytest tests/
```
