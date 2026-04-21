# StreetCheck Drug Supply Data Query
### Streamlit app — OPIC at Brandeis University

Natural language query interface for the drug checking dataset,
styled with StreetCheck brand colors.

---

## Setup (one-time)

**1. Open this folder in VS Code**

**2. Create a virtual environment**
```bash
python -m venv venv
source venv/bin/activate        # Mac / Linux
# venv\Scripts\activate         # Windows
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Add your API key**

Open `.env` and replace the placeholder:
```
ANTHROPIC_API_KEY=sk-ant-api03-...your key here...
```
Your key is at https://console.anthropic.com/keys

---

## Running

```bash
source venv/bin/activate
streamlit run app.py
```

The app opens automatically at **http://localhost:8501**

---

## How to use

1. Upload `VizDat_Updated.xlsx` using the sidebar file uploader
2. Click an example chip or type any question and press **Ask**
3. Results appear below — charts, tables, ranked lists, or plain answers

---

## Example questions

- Bar chart of top 10 active cuts in 2024
- Line chart of monthly Fentanyl sample count
- Pie chart of primary drug classes
- Table of sample counts by state
- List all unique active cuts detected
- % of cocaine samples that also contained fentanyl
- % of Medetomidine in Fentanyl-primary samples from Massachusetts
- Which state had the highest polysubstance rate?

---

## Project structure

```
drug-query-streamlit/
├── app.py                    # Main Streamlit application
├── .streamlit/
│   └── config.toml           # Theme colors and server config
├── .env                      # Your API key (never commit this)
├── requirements.txt          # Python dependencies
└── README.md
```

---

## Cost

Uses Claude Haiku 4.5 with prompt caching.
- First question per session: ~$0.002
- Subsequent questions (cache hit): ~$0.0015
- Typical monthly cost for moderate use: under $1.00

---

## Notes

- Analyses automatically filter to `status == "Complete"` rows
- Your Excel data is never sent to the API
- Results persist within the session; refresh to clear history
