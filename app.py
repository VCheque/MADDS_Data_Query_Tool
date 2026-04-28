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
    "Is Medetomidine independent of Xylazine in fentanyl-positive samples? Run a chi-square test",
    "Table of sample counts by state",
    "List all unique active cuts detected",
    "% of cocaine samples that also contained fentanyl",
    "Table of top 10 towns by sample count",
    "Which state had the highest polysubstance rate?",
    "% of Medetomidine in Fentanyl-primary samples from Massachusetts",
]

SYSTEM_PROMPT_TEMPLATE = """You are a data analyst for a harm reduction drug checking platform.
You analyze a Python pandas DataFrame called `df` ({total} rows total, {complete} with status "Complete").
Your job is to translate plain-English questions about the drug supply into reproducible pandas code
that produces a single JSON object describing the answer plus the right kind of visual.

COLUMN DEFINITIONS:
{schema}

ANALYSIS RULES:
- ALWAYS filter to df[df['status'] == 'Complete'] unless the question explicitly asks otherwise. The
  "Complete" subset is the only slice with fully coded lab columns; everything else is in-progress.
- acquired_date is a pandas datetime64 column. Use pd.to_datetime(..., errors='coerce') if you have any
  doubt about the dtype. For year filters use .dt.year; for month filters .dt.month; for date ranges
  use boolean masks like (df['acquired_date'] >= '2024-01-01') & (df['acquired_date'] < '2025-01-01').
- AllIllicits and ActiveCuts are comma-separated strings. Split with str.split(',') and trim each part
  with str.strip(). To count occurrences across rows, use .explode() after splitting into a list.
- confirmed_lab_substances and preliminary_ftir_substances are PIPE-separated (|), not comma-separated.
  Split on '|' and strip whitespace.
- All string comparisons must be case-insensitive. Prefer .str.lower() before equality checks, or
  .str.contains(..., case=False, na=False) for substring matching. Always pass na=False so NaN rows
  don't silently match.
- For percentages: round to 1 decimal place. When reporting a percent, also include the numerator and
  denominator in the answer text so the reader can sanity-check.
- Guard against NaN values with .dropna() on the relevant column, or .fillna('') for string columns
  before splitting. Never assume a column is fully populated.
- For monthly trends: use df['acquired_date'].dt.to_period('M').dt.to_timestamp() to get month-start
  datetimes that sort and plot correctly. For weekly, use .dt.to_period('W').
- For top-N rankings, use .value_counts().head(N). For ranked lists by a custom metric, use
  .groupby(...).agg(...).sort_values(..., ascending=False).head(N).
- For polysubstance analysis: a sample is "polysubstance" when its AllIllicits string contains a comma
  after stripping. Use df['AllIllicits'].fillna('').str.contains(',').
- When the user asks about a specific substance (e.g., Fentanyl, Cocaine, Xylazine, Medetomidine),
  match it inside AllIllicits using str.contains(name, case=False, na=False) on the comma-separated
  string. This catches both primary and secondary detections.

OUTPUT FORMAT — return a JSON object (and ONLY a JSON object, no markdown) with these fields:

  "answer"   string   Plain-English summary with specific numbers. Always required. Lead with the
                      headline number, then the context. Mention sample size and time window.
  "metrics"  array    Up to 4 objects {{label, value}} for headline numbers. Optional but encouraged
                      whenever the answer revolves around 1-4 key statistics.
  "chart"    object   Chart specification. Optional. See below.
  "table"    object   Table specification. Optional. See below.
  "list"     object   Ranked list. Optional. See below.
  "detail"   string   One-line methodology note explaining filters or assumptions. Optional but
                      encouraged when the analysis involved a non-obvious filter.

CHOOSE THE RIGHT OUTPUT TYPE:
- Rankings / top-N / distributions  ->  chart (bar) or list
- Trends over time                  ->  chart (line)
- Part-of-whole, up to 8 categories ->  chart (pie) with colors: true
- Multi-column comparisons          ->  table
- Simple enumeration                ->  list
- Single statistic                  ->  metrics only
- Statistical test result           ->  metrics for the test stat / p-value, plus answer text
                                        explaining what it means in plain English

CHART SPEC:
{{"type": "bar"|"line"|"pie", "labels": [...], "values": [...], "label": "Series name", "colors": true|false}}
  - labels and values must be the SAME LENGTH. Never return mismatched lengths.
  - For line charts of monthly trends, format labels as "Jan 2024", "Feb 2024", ... (use strftime("%b %Y")).
  - colors true  = one distinct color per bar/slice (good for categorical data with distinct groups)
  - colors false = all bars single teal color (good for ranked/ordered data of one type)

TABLE SPEC:
{{"headers": ["Col1", "Col2", ...], "rows": [["v", "v", ...], ...]}}  // max 50 rows
  - Convert all cell values to strings or simple types (int, float). No nested objects.
  - Format numbers with thousands separators in the answer text but keep raw numbers in the table cells.

LIST SPEC:
{{"items": [{{"label": "...", "value": "..."}}]}}  // max 20 items, sorted descending by numeric value

STATISTICAL TESTS YOU CAN RUN:
The user may ask for these directly. Use scipy.stats (already importable as scipy.stats) when needed.
Always return: the test statistic, the p-value, degrees of freedom (when applicable), and a one-sentence
plain-English interpretation. Use metrics for the numbers and answer for the interpretation.

  - Mann-Kendall trend test for monotonic trend over time (e.g., monthly fentanyl detections).
    Use scipy.stats.kendalltau on (month_index, monthly_count). Report tau and p-value.
  - Two-proportion z-test for comparing two percentages (e.g., xylazine rate in MA vs RI).
    Use statsmodels.stats.proportion.proportions_ztest, or compute manually with scipy.stats.norm.
  - Chi-square test of independence for categorical co-occurrence (e.g., DrugClass x State).
    Build a pandas crosstab then pass to scipy.stats.chi2_contingency. Report chi2, dof, p-value.
  - Fisher's exact test for 2x2 categorical with small counts. Use scipy.stats.fisher_exact.
  - Independent t-test or Mann-Whitney U for comparing two groups of counts.
    Use scipy.stats.ttest_ind or scipy.stats.mannwhitneyu. Mann-Whitney is safer for skewed counts.
  - Cohen's kappa for agreement between FTIR preliminary and confirmed lab substances.
    Use sklearn.metrics.cohen_kappa_score on aligned binary indicators per substance.
  - 95% confidence interval for a proportion: use statsmodels.stats.proportion.proportion_confint
    with method='wilson' (more accurate than normal approximation for small samples).

EXAMPLE PATTERNS (illustrative — not the actual data):

Question: "Top 5 active cuts in 2024"
Approach: filter Complete + year 2024 -> split ActiveCuts on "," -> explode -> strip -> drop empty
and "None Detected" -> value_counts -> head(5). Return as bar chart with colors:false. Include a
"detail" note: "Counts each appearance once per sample where the cut was detected."

Question: "What percent of cocaine samples also contained fentanyl in MA?"
Approach: filter Complete + state == "Massachusetts". Mask cocaine via
AllIllicits.str.contains("cocaine", case=False, na=False). Within that subset, mask fentanyl with the
same pattern. Compute (fent_count / coke_count) * 100, round to 1 decimal. Return metrics for
{{Cocaine Samples, Both Detected, Co-occurrence Rate}} plus a one-sentence answer.

Question: "Monthly fentanyl trend over the past year, with data labels"
Approach: filter Complete + AllIllicits contains fentanyl + last 12 months. Group by
acquired_date.dt.to_period('M'), count. Format labels as "Jan 2024" via strftime. Return as line chart.
Add metrics for {{Total Samples, Months with Data, Peak Month Count}}.

Question: "Run a chi-square test of independence between PrimaryDrugClass and StateofOriginCleaned"
Approach: filter Complete, drop NaNs in both columns, build pd.crosstab, pass to
scipy.stats.chi2_contingency. Return metrics for {{chi2, dof, p-value}} and an answer that
interprets the p-value: "p < 0.05 suggests drug class composition differs significantly across states."

IMPORTANT EXECUTION RULES:
- Write Python code using the DataFrame `df`, then end with: print(json.dumps(result, default=str))
- Import json at the top of your code. You may use pandas, numpy, json, scipy.stats, sklearn.metrics,
  and statsmodels — all are available.
- Print ONLY the final JSON. Do not include explanatory print statements, debug output, or markdown
  code fences in the printed output.
- Always wrap the final dict in json.dumps with default=str so datetime/Period values serialize cleanly.
- Keep label strings short enough to fit a chart axis (under ~30 characters each).
- For chart values, convert numpy ints/floats to native Python (int(x), float(x)) so JSON serializes.
- If the question is ambiguous, make a reasonable choice and explain it in the "detail" field rather
  than refusing to answer."""


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


_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "query_log.jsonl")


def _github_log_push(record_line: str) -> None:
    """Append one record to query_log.jsonl on GitHub. Silent on failure.

    Requires Streamlit secrets:
      GITHUB_TOKEN     fine-grained PAT with Contents: read & write
      GITHUB_LOG_REPO  e.g. "VCheque/MADDS_Data_Query_Tool"
    Optional:
      GITHUB_LOG_BRANCH (default: "logs")
      GITHUB_LOG_PATH   (default: "query_log.jsonl")
    """
    import urllib.request, urllib.error, base64

    token = _get_secret("GITHUB_TOKEN")
    repo = _get_secret("GITHUB_LOG_REPO")
    if not (token and repo):
        return
    branch = _get_secret("GITHUB_LOG_BRANCH") or "logs"
    path = _get_secret("GITHUB_LOG_PATH") or "query_log.jsonl"

    api = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "streetcheck-data-query",
    }

    def _attempt():
        sha = None
        current = b""
        try:
            req = urllib.request.Request(f"{api}?ref={branch}", headers=headers)
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
                sha = data["sha"]
                current = base64.b64decode(data["content"])
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
        new_content = current + record_line.encode("utf-8")
        payload = {
            "message": "log: append query",
            "content": base64.b64encode(new_content).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha
        req = urllib.request.Request(
            api,
            data=json.dumps(payload).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"},
            method="PUT",
        )
        urllib.request.urlopen(req, timeout=10).read()

    try:
        _attempt()
    except urllib.error.HTTPError as e:
        if e.code == 409:  # SHA conflict — retry once with fresh SHA
            try:
                _attempt()
            except Exception:
                pass
    except Exception:
        pass  # silent failure


def log_query(question: str, result: dict, df_rows: int) -> None:
    """Log a query both locally and to GitHub (background thread).

    Logs only the question text, timestamp, and execution metadata.
    Never logs the spreadsheet contents or generated code.
    """
    try:
        from datetime import datetime, timezone
        import threading
        usage = result.get("_usage", {}) or {}
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "question": question,
            "rows_in_dataset": df_rows,
            "success": result.get("_exec_error") is None,
            "exec_ms": round(result.get("_exec_seconds", 0.0) * 1000, 1),
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "cache_read": usage.get("cache_read", 0),
            "cache_creation": usage.get("cache_creation", 0),
            "error": result.get("_exec_error"),
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        # Local log (ephemeral on Streamlit Cloud, persistent locally)
        try:
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass
        # GitHub push (fire-and-forget; never blocks the user)
        threading.Thread(
            target=_github_log_push, args=(line,), daemon=True,
        ).start()
    except Exception:
        pass


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
        margin=dict(l=70, r=30, t=40, b=80),
        height=380,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Inter, sans-serif", color=COLORS["navy"], size=13),
    )
    axis_tickfont = dict(color=COLORS["navy"], size=12)

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
            xaxis=dict(tickangle=-30, showgrid=False, linecolor=COLORS["border"], tickfont=axis_tickfont),
            yaxis=dict(gridcolor=COLORS["border"], linecolor=COLORS["border"], tickfont=axis_tickfont),
            showlegend=False,
        )

    elif chart_type == "line":
        fig = go.Figure()
        fig.add_scatter(
            x=labels, y=values, name=label,
            mode="lines+markers",
            line_color=COLORS["teal"], line_width=2.5,
            marker_color=COLORS["teal"], marker_size=6,
        )
        fig.update_layout(
            **layout_base,
            xaxis=dict(tickangle=-30, showgrid=False, linecolor=COLORS["border"], tickfont=axis_tickfont),
            yaxis=dict(gridcolor=COLORS["border"], linecolor=COLORS["border"], tickfont=axis_tickfont),
        )

    elif chart_type == "pie":
        fig = go.Figure()
        fig.add_pie(
            labels=labels, values=values, hole=0.38,
            marker_colors=CAT_COLORS[:len(labels)],
            marker_line_color="white", marker_line_width=2,
            textinfo="label+percent", textfont_size=13,
        )
        fig.update_layout(**layout_base)

    else:
        fig = go.Figure()

    return fig


def fig_to_png_bytes(fig: go.Figure, width: int = 1200, height: int = 600) -> bytes:
    """Render a Plotly figure to PNG with explicit dimensions to avoid label cropping."""
    return fig.to_image(format="png", width=width, height=height, scale=2)


# ── Story-slide composer (1920x1080 PNG with answer + metrics + chart) ────────
def _get_slide_font(size: int, bold: bool = False):
    from PIL import ImageFont
    candidates = [
        # macOS
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        # Linux (Streamlit Cloud)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int, draw) -> list:
    """Word-wrap text to fit within max_width pixels."""
    words = str(text).split()
    if not words:
        return [""]
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


def compose_story_png(question: str, answer: str, metrics: list, fig: go.Figure) -> bytes:
    """Compose a 1920x1080 slide PNG with question, answer, metrics, and chart.

    Designed to drop straight onto a PowerPoint slide as a complete story.
    """
    from PIL import Image, ImageDraw
    from datetime import datetime

    W, H = 1920, 1080
    PAD = 60

    # Brand colors as RGB tuples
    NAVY    = (26, 43, 60)
    CARD    = (36, 53, 70)
    BORDER  = (60, 80, 100)
    TEAL    = (0, 133, 122)
    WHITE   = (255, 255, 255)
    MUTED   = (180, 190, 200)

    img = Image.new("RGB", (W, H), NAVY)
    draw = ImageDraw.Draw(img)

    f_q  = _get_slide_font(20, bold=True)
    f_a  = _get_slide_font(30)
    f_ml = _get_slide_font(15, bold=True)
    f_mv = _get_slide_font(60, bold=True)
    f_ft = _get_slide_font(15)

    card_x, card_y, card_w = PAD, PAD, W - 2 * PAD
    inner_pad = 32

    # ─── Question + Answer card ──────────────────────────────────────
    q_lines = _wrap_text(question.upper(), f_q, card_w - 2 * inner_pad, draw)
    a_lines = _wrap_text(answer or "", f_a, card_w - 2 * inner_pad, draw)
    line_h_q, line_h_a = 30, 44
    qa_h = inner_pad + len(q_lines) * line_h_q + 14 + 14 + len(a_lines) * line_h_a + inner_pad

    draw.rounded_rectangle(
        [card_x, card_y, card_x + card_w, card_y + qa_h],
        radius=14, fill=CARD, outline=BORDER, width=1,
    )
    y = card_y + inner_pad
    for line in q_lines:
        draw.text((card_x + inner_pad, y), line, font=f_q, fill=MUTED)
        y += line_h_q
    y += 8
    draw.line(
        [(card_x + inner_pad, y), (card_x + card_w - inner_pad, y)],
        fill=BORDER, width=1,
    )
    y += 14
    for line in a_lines:
        draw.text((card_x + inner_pad, y), line, font=f_a, fill=WHITE)
        y += line_h_a

    # ─── Metric cards row ────────────────────────────────────────────
    metrics = (metrics or [])[:4]
    metric_y = card_y + qa_h + 24
    metric_h = 0
    if metrics:
        metric_h = 140
        gap = 20
        mw = (card_w - (len(metrics) - 1) * gap) // len(metrics)
        for i, m in enumerate(metrics):
            mx = card_x + i * (mw + gap)
            draw.rounded_rectangle(
                [mx, metric_y, mx + mw, metric_y + metric_h],
                radius=10, fill=CARD, outline=BORDER, width=1,
            )
            draw.text((mx + 24, metric_y + 22), str(m.get("label", "")).upper(), font=f_ml, fill=MUTED)
            draw.text((mx + 24, metric_y + 54), str(m.get("value", "")), font=f_mv, fill=TEAL)

    # ─── Chart (rendered with dark theme to match the slide) ─────────
    chart_y = metric_y + (metric_h + 24 if metric_h else 0)
    chart_h = H - chart_y - PAD - 30
    chart_w = card_w

    fig_dark = go.Figure(fig)
    fig_dark.update_layout(
        plot_bgcolor="#243546",
        paper_bgcolor="#243546",
        font=dict(family="Arial, sans-serif", color="#FFFFFF", size=18),
        xaxis=dict(
            tickfont=dict(color="#FFFFFF", size=15),
            linecolor="#506070", gridcolor="#506070",
        ),
        yaxis=dict(
            tickfont=dict(color="#FFFFFF", size=15),
            linecolor="#506070", gridcolor="#506070",
        ),
        margin=dict(l=90, r=40, t=40, b=110),
    )
    chart_png = fig_dark.to_image(format="png", width=chart_w, height=chart_h, scale=2)
    chart_img = Image.open(io.BytesIO(chart_png)).convert("RGB")
    chart_img = chart_img.resize((chart_w, chart_h), Image.LANCZOS)
    img.paste(chart_img, (card_x, chart_y))

    # ─── Footer ──────────────────────────────────────────────────────
    footer = (
        f"StreetCheck Drug Supply Data Query  \u00B7  OPIC at Brandeis University  "
        f"\u00B7  {datetime.now().strftime('%Y-%m-%d')}"
    )
    draw.text((PAD, H - PAD + 6), footer, font=f_ft, fill=MUTED)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


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
    st.caption("Data stays in your session.\n")


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


def submit_question():
    """Capture the question and clear the input box (must run before the next rerun)."""
    q = st.session_state.get("question_input", "").strip()
    if q:
        st.session_state["_pending_question"] = q
        st.session_state["question_input"] = ""


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
    st.button("Ask →", type="primary", use_container_width=True, on_click=submit_question)

# ── Run query ─────────────────────────────────────────────────────────────────
pending_question = st.session_state.pop("_pending_question", None)
if pending_question:
    with st.spinner("Analyzing..."):
        result = run_query(client, df, pending_question)
    log_query(pending_question, result, df_rows=len(df))
    if "history" not in st.session_state:
        st.session_state["history"] = []
    st.session_state["history"].insert(0, (pending_question, result))

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
        chart_spec = result.get("chart") or {}
        chart_labels = chart_spec.get("labels") or []
        chart_values = chart_spec.get("values") or []
        chart_renderable = (
            chart_spec
            and chart_labels
            and chart_values
            and len(chart_labels) == len(chart_values)
        )
        if chart_spec and not chart_renderable:
            st.info("⚠️ The analysis didn't return enough chart data. Try rephrasing your question or being more specific.")
        if chart_renderable:
            fig = make_chart(chart_spec)
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{idx}")

            # Download buttons for chart
            dl1, dl2, dl3, dl4 = st.columns([1, 1, 1, 5])
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
                except Exception as e:
                    st.caption(f"⚠ PNG unavailable: {type(e).__name__}: {e}")
            with dl2:
                labels = chart_spec.get("labels", []) or []
                values = chart_spec.get("values", []) or []
                # Pad the shorter list with None so DataFrame construction never
                # crashes when the model returns mismatched labels/values.
                n = max(len(labels), len(values))
                labels = list(labels) + [None] * (n - len(labels))
                values = list(values) + [None] * (n - len(values))
                if n > 0:
                    chart_df = pd.DataFrame({
                        chart_spec.get("label", "value"): values,
                    }, index=labels)
                    chart_df.index.name = "label"
                    st.markdown('<div class="dl-btn">', unsafe_allow_html=True)
                    st.download_button(
                        "⬇ CSV",
                        data=df_to_csv_bytes(chart_df.reset_index()),
                        file_name=f"chart_{idx+1}.csv",
                        mime="text/csv",
                        key=f"dl_chart_csv_{idx}",
                    )
                    st.markdown('</div>', unsafe_allow_html=True)
            with dl3:
                try:
                    slide_bytes = compose_story_png(
                        question=q,
                        answer=result.get("answer", ""),
                        metrics=result.get("metrics", []),
                        fig=fig,
                    )
                    st.markdown('<div class="dl-btn">', unsafe_allow_html=True)
                    st.download_button(
                        "⬇ Slide",
                        data=slide_bytes,
                        file_name=f"slide_{idx+1}.png",
                        mime="image/png",
                        key=f"dl_slide_{idx}",
                        help="1920×1080 PowerPoint-ready slide with the answer, metrics, and chart bundled together.",
                    )
                    st.markdown('</div>', unsafe_allow_html=True)
                except Exception as e:
                    st.caption(f"⚠ Slide unavailable: {type(e).__name__}: {e}")

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
            elif cache_write > 0:
                badge = f'<span class="cache-miss">cache write</span> — {cache_write:,} tokens cached for next call'
            else:
                badge = '<span class="cache-miss">cache inactive</span> — prompt below cache threshold'
            st.markdown(
                f'<div class="token-badge">{badge} &nbsp;·&nbsp; '
                f'{usage.get("input_tokens",0):,} in &nbsp;·&nbsp; '
                f'{usage.get("output_tokens",0):,} out</div>',
                unsafe_allow_html=True,
            )

        st.markdown("---")
