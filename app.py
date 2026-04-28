import os
import io
import json
import re
import base64
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="StreetCheck Data Query",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Helpers (secrets) ─────────────────────────────────────────────────────────
def _get_secret(name: str, default: str = "") -> str:
    """Read from env vars first, then Streamlit secrets (for Cloud deployment)."""
    val = os.environ.get(name, "")
    if not val:
        try:
            val = st.secrets.get(name, default)
        except Exception:
            val = default
    return val


# ── Microsoft Clarity ─────────────────────────────────────────────────────────
import streamlit.components.v1 as components

_CLARITY_ID = _get_secret("CLARITY_PROJECT_ID")
if _CLARITY_ID:
    components.html(f"""
    <script type="text/javascript">
        try {{
            var p = window.parent;
            if (!p.clarity) {{
                p.clarity = function() {{
                    (p.clarity.q = p.clarity.q || []).push(arguments);
                }};
                var s = p.document.createElement('script');
                s.async = true;
                s.src = 'https://www.clarity.ms/tag/{_CLARITY_ID}';
                p.document.head.appendChild(s);
            }}
        }} catch(e) {{
            // Cross-origin fallback: inject into this iframe instead
            (function(c,l,a,r,i,t,y){{
                c[a]=c[a]||function(){{(c[a].q=c[a].q||[]).push(arguments)}};
                t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
                y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
            }})(window, document, "clarity", "script", "{_CLARITY_ID}");
        }}
    </script>
    """, height=0)


# ── Brand colors ──────────────────────────────────────────────────────────────
COLORS = {
    "teal":       "#00857A",
    "teal_light": "#E6F4F3",
    "teal_dark":  "#005F57",
    "navy":       "#1A2B3C",
    "orange":     "#E8601C",
    "muted":      "#5A6A7A",
    "border":     "#D0D8E0",
    "bg":         "#243546",
    "white":      "#FFFFFF",
}

CAT_COLORS = [
    "#00857A","#1A2B3C","#E8601C","#4A90D9",
    "#8B5CF6","#059669","#D97706","#DC2626",
    "#7C3AED","#0891B2",
]

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}

  .stApp {{
      background: {COLORS['navy']};
  }}
  .stApp, .stApp [data-testid="stMarkdownContainer"] p,
  .stApp [data-testid="stMarkdownContainer"] h4,
  .stApp label, .stApp .stMetric label, .stApp .stMetric [data-testid="stMetricValue"] {{
      color: {COLORS['white']} !important;
  }}

  .sc-header {{
      background: rgba(255,255,255,0.08);
      padding: 1rem 1.5rem;
      border-radius: 10px;
      margin-bottom: 1.5rem;
      display: flex;
      align-items: center;
      gap: 18px;
      border: 1px solid rgba(255,255,255,0.12);
  }}
  .sc-header-text h1 {{
      font-size: 20px; font-weight: 700;
      color: white; margin: 0; letter-spacing: -0.02em;
  }}
  .sc-header-text p {{
      font-size: 12px; color: rgba(255,255,255,0.6); margin: 3px 0 0;
  }}

  .result-card {{
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.10);
      border-radius: 10px;
      padding: 1.25rem 1.5rem;
      margin-bottom: 0.5rem;
  }}
  .result-question {{
      font-size: 11px; font-weight: 600;
      color: rgba(255,255,255,0.5);
      text-transform: uppercase; letter-spacing: 0.06em;
      margin-bottom: 8px; padding-bottom: 8px;
      border-bottom: 1px solid rgba(255,255,255,0.10);
  }}
  .result-answer {{
      font-size: 16px; color: {COLORS['white']}; line-height: 1.65; margin: 0;
  }}

  .metric-card {{
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.10);
      border-radius: 8px;
      padding: 12px 18px;
  }}
  .metric-label {{
      font-size: 11px; font-weight: 600;
      color: rgba(255,255,255,0.5);
      text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;
  }}
  .metric-value {{
      font-size: 24px; font-weight: 700; color: {COLORS['teal']};
  }}

  .token-badge {{
      font-size: 11px; color: rgba(255,255,255,0.45);
      margin-top: 10px; padding-top: 10px;
      border-top: 1px solid rgba(255,255,255,0.10);
  }}
  .cache-hit   {{ color: {COLORS['teal']}; font-weight: 600; }}
  .cache-miss  {{ color: rgba(255,255,255,0.45); }}

  .val-list {{ margin-top: 10px; }}
  .val-item {{
      display: flex; align-items: center; gap: 10px;
      padding: 5px 0; font-size: 13px;
      border-bottom: 1px solid rgba(255,255,255,0.10);
  }}
  .val-item:last-child {{ border-bottom: none; }}
  .val-rank  {{ color: rgba(255,255,255,0.45); min-width: 22px; font-size: 11px; text-align: right; }}
  .val-label {{ flex: 1; color: {COLORS['white']}; }}
  .val-num   {{ font-weight: 600; color: {COLORS['teal']}; min-width: 70px; text-align: right; }}

  section[data-testid="stSidebar"] {{ background: #12202E !important; }}
  section[data-testid="stSidebar"] * {{ color: white !important; }}
  section[data-testid="stSidebar"] .stMarkdown p {{ color: rgba(255,255,255,0.65) !important; font-size: 13px; }}

  #MainMenu {{ visibility: hidden; }}
  footer     {{ visibility: hidden; }}
  header     {{ visibility: hidden; }}

  .stTextArea textarea {{
      background: rgba(255,255,255,0.06) !important;
      color: white !important;
      border: 1.5px solid rgba(255,255,255,0.15); border-radius: 8px; font-size: 14px;
  }}
  .stTextArea textarea:focus {{
      border-color: {COLORS['teal']};
      box-shadow: 0 0 0 3px rgba(0,133,122,0.25);
  }}
  .stButton > button {{
      background: {COLORS['teal']}; color: white; border: none;
      border-radius: 8px; font-weight: 600; font-size: 14px;
  }}
  .stButton > button:hover {{ background: {COLORS['teal_dark']}; color: white; }}

  /* Download button -- outlined style */
  .dl-btn > button {{
      background: transparent !important;
      color: {COLORS['teal']} !important;
      border: 1.5px solid {COLORS['teal']} !important;
      border-radius: 6px;
      font-size: 12px;
      padding: 3px 12px;
  }}
  .dl-btn > button:hover {{
      background: rgba(0,133,122,0.15) !important;
  }}

  /* Horizontal rules */
  hr {{ border-color: rgba(255,255,255,0.10) !important; }}
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
RELEVANT_COLS = [
    "acquired_date","groupid","tenantid","town","suspected",
    "confirmed_lab_substances","preliminary_ftir_substances",
    "TownofOriginCleaned","CountyofOriginCleaned","StateofOriginCleaned",
    "PrimaryIllicit","AllIllicits","ActiveCuts","SuspectedCleaned",
    "DrugClasses","PrimaryDrugClass","status",
]

SCHEMA_DESCRIPTION = """
- acquired_date: datetime the sample was acquired.
- groupid: collection group/site identifier.
- tenantid: tenant/organisation identifier.
- town: free-text town name as submitted.
- suspected: free-text suspected substance(s) as reported by submitter.
- confirmed_lab_substances: pipe-separated substances confirmed by lab e.g. "Fentanyl|Heroin|Caffeine".
- preliminary_ftir_substances: pipe-separated FTIR preliminary substances.
- TownofOriginCleaned: cleaned town name.
- CountyofOriginCleaned: cleaned county name.
- StateofOriginCleaned: full US state name e.g. "Massachusetts", "Rhode Island".
- PrimaryIllicit: single primary illicit substance e.g. "Fentanyl", "Cocaine", "None Detected".
- AllIllicits: comma-separated all illicit substances e.g. "Fentanyl, Heroin". Split on "," and trim.
- ActiveCuts: comma-separated active adulterants e.g. "Xylazine, Caffeine" or "None Detected". Split on "," and trim.
- SuspectedCleaned: cleaned suspected substance.
- DrugClasses: comma-separated drug classes e.g. "Opioid, Stimulant".
- PrimaryDrugClass: drug class of PrimaryIllicit e.g. "Opioid", "Stimulant", "Benzodiazepine".
- status: Only "Complete" rows have fully coded lab columns. Values: Complete, Tested, Initial, Untested.
""".strip()

EXAMPLES = [
    "Bar chart of top 10 active cuts in 2024",
    "Line chart of monthly Fentanyl sample count",
    "Pie chart of primary drug classes",
    "Table of sample counts by state",
    "List all unique active cuts detected",
    "% of cocaine samples that also contained fentanyl",
    "Table of top 10 towns by sample count",
    "Which state had the highest polysubstance rate?",
    "% of Medetomidine in Fentanyl-primary samples from Massachusetts",
]

SYSTEM_PROMPT_TEMPLATE = """You are a data analyst for a harm reduction drug checking platform.
You analyze a Python pandas DataFrame called `df` ({total} rows total, {complete} with status "Complete").

COLUMN DEFINITIONS:
{schema}

ANALYSIS RULES:
- ALWAYS filter to df[df['status'] == 'Complete'] unless the question says otherwise.
- acquired_date is a pandas datetime column. Use pd.to_datetime() if needed.
- AllIllicits and ActiveCuts are comma-separated strings. Use str.split(',') and str.strip().
- All string comparisons must be case-insensitive. Use .str.lower() or .str.contains(..., case=False).
- For percentages: round to 1 decimal place.
- Guard against NaN values with .dropna() or .fillna('').
- For monthly trends: use df['acquired_date'].dt.to_period('M').

OUTPUT FORMAT — return a JSON object (and ONLY a JSON object, no markdown) with these fields:

  "answer"   string   Plain-English summary with specific numbers. Always required.
  "metrics"  array    Up to 4 objects {{label, value}} for headline numbers. Optional.
  "chart"    object   Chart specification. Optional. See below.
  "table"    object   Table specification. Optional. See below.
  "list"     object   Ranked list. Optional. See below.
  "detail"   string   One-line methodology note. Optional.

CHOOSE THE RIGHT OUTPUT TYPE:
- Rankings / top-N / distributions  ->  chart (bar) or list
- Trends over time                  ->  chart (line)
- Part-of-whole, up to 8 categories ->  chart (pie) with colors: true
- Multi-column comparisons          ->  table
- Simple enumeration                ->  list
- Single statistic                  ->  metrics only

CHART SPEC:
{{"type": "bar"|"line"|"pie", "labels": [...], "values": [...], "label": "Series name", "colors": true|false}}
  colors true  = one distinct color per bar/slice
  colors false = all bars single teal color

TABLE SPEC:
{{"headers": ["Col1", "Col2", ...], "rows": [["v", "v", ...], ...]}}  // max 50 rows

LIST SPEC:
{{"items": [{{"label": "...", "value": "..."}}]}}  // max 20 items, sorted descending

IMPORTANT: Write Python code using the DataFrame `df`, then end with: print(json.dumps(result))
Import json at the top. Use only pandas, numpy, json. Print ONLY the final JSON."""


# ── Helpers ───────────────────────────────────────────────────────────────────
@st.cache_resource
def get_client():
    key = _get_secret("ANTHROPIC_API_KEY")
    if not key or key == "your_api_key_here":
        return None
    return Anthropic(api_key=key)


@st.cache_data
def load_data(file_bytes: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    available = [c for c in RELEVANT_COLS if c in df.columns]
    df = df[available].copy()
    if "acquired_date" in df.columns:
        df["acquired_date"] = pd.to_datetime(df["acquired_date"], errors="coerce")
    return df


def run_query(client: Anthropic, df: pd.DataFrame, question: str) -> dict:
    import time
    complete = df[df["status"] == "Complete"] if "status" in df.columns else df
    system = SYSTEM_PROMPT_TEMPLATE.format(
        total=len(df), complete=len(complete), schema=SCHEMA_DESCRIPTION
    )
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=[{"type":"text","text":system,"cache_control":{"type":"ephemeral"}}],
        messages=[{"role":"user","content":question}],
    )
    usage = response.usage
    raw = re.sub(r"^```[\w]*\n?","",response.content[0].text.strip()).rstrip("`").strip()

    buf = io.StringIO()
    import contextlib
    local_vars = {"df": df.copy(), "pd": pd, "json": json}
    exec_error = None
    exec_seconds = 0.0
    try:
        import numpy as np
        local_vars["np"] = np
        t0 = time.perf_counter()
        with contextlib.redirect_stdout(buf):
            exec(raw, local_vars)
        exec_seconds = time.perf_counter() - t0
        output = buf.getvalue().strip()
        if not output:
            raise ValueError("Model returned code that produced no output")
        result = json.loads(output)
    except json.JSONDecodeError as e:
        exec_error = f"Invalid JSON: {e}"
        result = {"answer": f"Analysis returned invalid JSON. Raw output: {buf.getvalue().strip()[:500]}"}
    except Exception as e:
        exec_error = f"{type(e).__name__}: {e}"
        result = {"answer": f"Error executing analysis: {e}", "detail": raw[:500]}

    result["_usage"] = {
        "input_tokens":  usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_creation": getattr(usage,"cache_creation_input_tokens",0),
        "cache_read":     getattr(usage,"cache_read_input_tokens",0),
    }
    result["_code"] = raw
    result["_stdout"] = buf.getvalue()
    result["_exec_seconds"] = exec_seconds
    result["_exec_error"] = exec_error
    return result


def make_chart(spec: dict) -> go.Figure:
    """Build a Plotly figure from a chart spec dict."""
    chart_type = spec.get("type","bar")
    labels     = spec.get("labels",[])
    values     = spec.get("values",[])
    label      = spec.get("label","")
    use_colors = spec.get("colors", False)

    layout_base = dict(
        margin=dict(l=10,r=10,t=30,b=10),
        height=320,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Inter, sans-serif", color=COLORS["navy"], size=12),
    )

    if chart_type == "bar":
        bar_colors = (
            [CAT_COLORS[i % len(CAT_COLORS)] for i in range(len(labels))]
            if use_colors else [COLORS["teal"]] * len(labels)
        )
        fig = go.Figure()
        fig.add_bar(
            x=labels, y=values, name=label,
            marker_color=bar_colors, marker_line_width=0,
        )
        fig.update_layout(
            **layout_base,
            xaxis=dict(tickangle=-35, showgrid=False, linecolor=COLORS["border"]),
            yaxis=dict(gridcolor=COLORS["border"], linecolor=COLORS["border"]),
            showlegend=False,
        )

    elif chart_type == "line":
        fig = go.Figure()
        fig.add_scatter(
            x=labels, y=values, name=label,
            mode="lines+markers",
            line_color=COLORS["teal"], line_width=2.5,
            marker_color=COLORS["teal"], marker_size=5,
        )
        fig.update_layout(
            **layout_base,
            xaxis=dict(tickangle=-35, showgrid=False, linecolor=COLORS["border"]),
            yaxis=dict(gridcolor=COLORS["border"], linecolor=COLORS["border"]),
        )

    elif chart_type == "pie":
        fig = go.Figure()
        fig.add_pie(
            labels=labels, values=values, hole=0.38,
            marker_colors=CAT_COLORS[:len(labels)],
            marker_line_color="white", marker_line_width=2,
            textinfo="label+percent", textfont_size=12,
        )
        fig.update_layout(**layout_base)

    else:
        fig = go.Figure()

    return fig


def fig_to_png_bytes(fig: go.Figure) -> bytes:
    return fig.to_image(format="png", scale=2)


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def df_to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False)
    return buf.getvalue()


_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def logo_b64() -> str:
    for directory in (_SCRIPT_DIR, os.getcwd()):
        logo_path = os.path.join(directory, "streetcheck_logo.png")
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as f:
                return base64.b64encode(f.read()).decode()
    return ""


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    logo = logo_b64()
    if logo:
        st.markdown(
            f'<img src="data:image/png;base64,{logo}" style="width:100%;max-width:220px;margin-bottom:1rem;">',
            unsafe_allow_html=True,
        )
    else:
        st.markdown("## 🔬 StreetCheck")

    st.markdown("**Data Query Tool**")
    st.markdown("---")
    st.markdown("### Upload data")
    uploaded = st.file_uploader(
        "Drop your Excel file here",
        type=["xlsx"],
        label_visibility="collapsed",
    )
    if uploaded:
        st.success(f"✓ {uploaded.name}")

    st.markdown("---")
    st.markdown("### About")
    st.markdown(
        "Ask questions about the drug supply dataset in plain English. "
        "Results can be charts, tables, ranked lists, or key metrics -- "
        "all downloadable."
    )
    st.markdown("---")
    st.markdown("### Example questions")
    for ex in EXAMPLES[:5]:
        st.markdown(f"- {ex}")
    st.markdown("---")
    st.caption("Data stays in your session.\nOnly your question is sent to the API.")


# ── Header ────────────────────────────────────────────────────────────────────
logo = logo_b64()
logo_html = (
    f'<img src="data:image/png;base64,{logo}" style="height:52px;">'
    if logo else '<span style="font-size:32px;">🔬</span>'
)
st.markdown(f"""
<div class="sc-header">
  {logo_html}
  <div class="sc-header-text">
    <h1>Drug Supply Data Query</h1>
    <p>Powered by StreetCheck &nbsp;·&nbsp; MADDS at Brandeis University</p>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Guards ────────────────────────────────────────────────────────────────────
client = get_client()
if client is None:
    st.error("⚠️  No API key found. Add your Anthropic API key to the `.env` file.")
    st.code("ANTHROPIC_API_KEY=sk-ant-api03-...")
    st.stop()

if uploaded is None:
    st.info("👈  Upload your Excel file in the sidebar to get started.")
    st.stop()

# Cache file bytes in session_state so re-runs don't re-read an exhausted file object
if uploaded is not None:
    if st.session_state.get("file_name") != uploaded.name:
        st.session_state["file_bytes"] = uploaded.read()
        st.session_state["file_name"] = uploaded.name

df = load_data(st.session_state["file_bytes"])
complete_count = int((df["status"] == "Complete").sum()) if "status" in df.columns else len(df)

c1, c2, c3 = st.columns(3)
c1.metric("Total rows",     f"{len(df):,}")
c2.metric("Complete rows",  f"{complete_count:,}")
c3.metric("Columns loaded", f"{len(df.columns)}")

st.markdown("---")

# ── Example chips ─────────────────────────────────────────────────────────────
st.markdown("#### Ask a question")


def set_example(text: str):
    st.session_state["question_input"] = text


ex_cols = st.columns(4)
for i, ex in enumerate(EXAMPLES[:4]):
    with ex_cols[i]:
        st.button(ex, key=f"ex_{i}", use_container_width=True,
                  on_click=set_example, args=(ex,))

st.text_area(
    "question",
    key="question_input",
    placeholder="e.g. Bar chart of top 10 active cuts in 2024",
    height=80,
    label_visibility="collapsed",
)

ask_col, _ = st.columns([1, 6])
with ask_col:
    ask = st.button("Ask →", type="primary", use_container_width=True)

# ── Run query ─────────────────────────────────────────────────────────────────
question = st.session_state.get("question_input", "")
if ask and question.strip():
    with st.spinner("Analyzing..."):
        result = run_query(client, df, question.strip())
    if "history" not in st.session_state:
        st.session_state["history"] = []
    st.session_state["history"].insert(0, (question.strip(), result))

# ── Render history ────────────────────────────────────────────────────────────
if st.session_state.get("history"):
    st.markdown("---")
    st.markdown("#### Results")

    for idx, (q, result) in enumerate(st.session_state["history"]):
        usage = result.get("_usage", {})

        # ── Answer card ───────────────────────────────────────────────────────
        st.markdown(f"""
        <div class="result-card">
          <div class="result-question">{q}</div>
          <p class="result-answer">{result.get('answer','')}</p>
        </div>""", unsafe_allow_html=True)

        # ── Metrics ───────────────────────────────────────────────────────────
        metrics = result.get("metrics", [])
        if metrics:
            mc = st.columns(min(len(metrics), 4))
            for mi, m in enumerate(metrics[:4]):
                with mc[mi]:
                    st.markdown(f"""
                    <div class="metric-card">
                      <div class="metric-label">{m.get('label','')}</div>
                      <div class="metric-value">{m.get('value','')}</div>
                    </div>""", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

        # ── Chart ─────────────────────────────────────────────────────────────
        if result.get("chart"):
            fig = make_chart(result["chart"])
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{idx}")

            # Download buttons for chart
            dl1, dl2, dl3 = st.columns([1, 1, 6])
            with dl1:
                try:
                    png_bytes = fig_to_png_bytes(fig)
                    st.markdown('<div class="dl-btn">', unsafe_allow_html=True)
                    st.download_button(
                        "⬇ PNG",
                        data=png_bytes,
                        file_name=f"chart_{idx+1}.png",
                        mime="image/png",
                        key=f"dl_png_{idx}",
                    )
                    st.markdown('</div>', unsafe_allow_html=True)
                except Exception:
                    pass  # kaleido not installed — skip PNG download
            with dl2:
                st.markdown('<div class="dl-btn">', unsafe_allow_html=True)
                chart_spec = result["chart"]
                chart_df = pd.DataFrame({
                    chart_spec.get("label","value"): chart_spec.get("values",[]),
                }, index=chart_spec.get("labels",[]))
                chart_df.index.name = "label"
                st.download_button(
                    "⬇ CSV",
                    data=df_to_csv_bytes(chart_df.reset_index()),
                    file_name=f"chart_{idx+1}.csv",
                    mime="text/csv",
                    key=f"dl_chart_csv_{idx}",
                )
                st.markdown('</div>', unsafe_allow_html=True)

        # ── Table ─────────────────────────────────────────────────────────────
        if result.get("table"):
            tbl = result["table"]
            headers = tbl.get("headers", [])
            rows    = tbl.get("rows", [])
            if headers and rows:
                tdf = pd.DataFrame(rows, columns=headers)
                st.dataframe(tdf, use_container_width=True, hide_index=True)

                # Download buttons for table
                dl1, dl2, dl3 = st.columns([1, 1, 6])
                with dl1:
                    st.markdown('<div class="dl-btn">', unsafe_allow_html=True)
                    st.download_button(
                        "⬇ CSV",
                        data=df_to_csv_bytes(tdf),
                        file_name=f"table_{idx+1}.csv",
                        mime="text/csv",
                        key=f"dl_tbl_csv_{idx}",
                    )
                    st.markdown('</div>', unsafe_allow_html=True)
                with dl2:
                    st.markdown('<div class="dl-btn">', unsafe_allow_html=True)
                    st.download_button(
                        "⬇ Excel",
                        data=df_to_excel_bytes(tdf),
                        file_name=f"table_{idx+1}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_tbl_xlsx_{idx}",
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

        # ── Value list ────────────────────────────────────────────────────────
        if result.get("list"):
            items = result["list"].get("items", [])
            if items:
                nums = []
                for item in items:
                    try:
                        nums.append(float(re.sub(r"[^0-9.]","",str(item.get("value","0")))))
                    except Exception:
                        nums.append(0.0)
                max_val = max(nums) if nums else 1

                list_html = '<div class="val-list">'
                for i, item in enumerate(items):
                    pct = int((nums[i] / max_val) * 100) if max_val else 0
                    list_html += f"""
                    <div class="val-item">
                      <span class="val-rank">{i+1}</span>
                      <span class="val-label">{item.get('label','')}</span>
                      <div style="flex:1;background:rgba(255,255,255,0.10);border-radius:3px;height:6px;overflow:hidden;">
                        <div style="width:{pct}%;height:100%;background:{COLORS['teal']};border-radius:3px;"></div>
                      </div>
                      <span class="val-num">{item.get('value','')}</span>
                    </div>"""
                list_html += "</div>"
                st.markdown(list_html, unsafe_allow_html=True)

                # Download list as CSV
                list_df = pd.DataFrame(items)
                dl1, dl2 = st.columns([1, 7])
                with dl1:
                    st.markdown('<div class="dl-btn">', unsafe_allow_html=True)
                    st.download_button(
                        "⬇ CSV",
                        data=df_to_csv_bytes(list_df),
                        file_name=f"list_{idx+1}.csv",
                        mime="text/csv",
                        key=f"dl_list_{idx}",
                    )
                    st.markdown('</div>', unsafe_allow_html=True)

        # ── Detail note ───────────────────────────────────────────────────────
        if result.get("detail"):
            st.caption(f"ℹ️ {result['detail']}")

        # ── Token usage ───────────────────────────────────────────────────────
        if usage:
            cache_read  = usage.get("cache_read", 0)
            cache_write = usage.get("cache_creation", 0)
            if cache_read > 0:
                badge = f'<span class="cache-hit">⚡ cache hit</span> — {cache_read:,} tokens read from cache'
            else:
                badge = f'<span class="cache-miss">cache write</span> — {cache_write:,} tokens cached for next call'
            st.markdown(
                f'<div class="token-badge">{badge} &nbsp;·&nbsp; '
                f'{usage.get("input_tokens",0):,} in &nbsp;·&nbsp; '
                f'{usage.get("output_tokens",0):,} out</div>',
                unsafe_allow_html=True,
            )

        # ── Generated Python code + execution details ─────────────────────────
        code = result.get("_code", "")
        stdout = result.get("_stdout", "")
        exec_seconds = result.get("_exec_seconds", 0.0)
        exec_error = result.get("_exec_error")
        if code:
            label = f"View generated code (ran in {exec_seconds*1000:.0f} ms)"
            if exec_error:
                label = f"⚠ View generated code — {exec_error}"
            with st.expander(label):
                st.markdown("**Python code Claude wrote and executed against your DataFrame:**")
                st.code(code, language="python")
                st.markdown('<div class="dl-btn">', unsafe_allow_html=True)
                st.download_button(
                    "⬇ Python",
                    data=code.encode("utf-8"),
                    file_name=f"query_{idx+1}.py",
                    mime="text/x-python",
                    key=f"dl_py_{idx}",
                )
                st.markdown('</div>', unsafe_allow_html=True)
                if stdout:
                    st.markdown("**Captured stdout (the JSON the code printed):**")
                    st.code(stdout.strip(), language="json")

        # ── Raw JSON response ─────────────────────────────────────────────────
        internal_keys = {"_usage", "_code", "_stdout", "_exec_seconds", "_exec_error"}
        json_payload = {k: v for k, v in result.items() if k not in internal_keys}
        json_payload["_question"] = q
        json_str = json.dumps(json_payload, indent=2, default=str)
        with st.expander("View JSON response"):
            st.json(json_payload)
            st.markdown('<div class="dl-btn">', unsafe_allow_html=True)
            st.download_button(
                "⬇ JSON",
                data=json_str.encode("utf-8"),
                file_name=f"response_{idx+1}.json",
                mime="application/json",
                key=f"dl_json_{idx}",
            )
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("---")
