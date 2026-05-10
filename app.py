import streamlit as st
from pypdf import PdfReader
import json
import re
import time
import anthropic
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Fact-Check Agent",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styles ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .stApp { background: #0A1628; }
  h1, h2, h3, p, label, .stMarkdown { color: #E2E8F0 !important; }
  .claim-card { border-radius: 10px; padding: 18px 20px; margin: 12px 0;
                border-left: 5px solid; background: #0D2137; }
  .verified   { border-color: #10B981; }
  .inaccurate { border-color: #F59E0B; }
  .false      { border-color: #EF4444; }
  .unverified { border-color: #6B7280; }
  .badge { display:inline-block; padding:3px 10px; border-radius:20px;
           font-size:12px; font-weight:700; margin-bottom:8px; }
  .badge-verified   { background:#065F46; color:#6EE7B7; }
  .badge-inaccurate { background:#78350F; color:#FDE68A; }
  .badge-false      { background:#7F1D1D; color:#FCA5A5; }
  .badge-unverified { background:#374151; color:#9CA3AF; }
  .metric-box { background:#0D2137; border-radius:10px; padding:16px;
                text-align:center; border:1px solid #1E3A5F; }
  .metric-num { font-size:36px; font-weight:800; }
  .source-link a { color:#38BDF8 !important; font-size:12px; }
  div[data-testid="stFileUploader"] { background:#0D2137; border-radius:10px;
    border:2px dashed #1E3A5F; padding:16px; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("## 🔍 Fact-Check Agent")
st.markdown("*Upload a PDF — the agent extracts claims, cross-references live web data, and flags inaccuracies.*")
st.divider()

# ── Helpers ───────────────────────────────────────────────────────────────────
def extract_text_from_pdf(uploaded_file) -> str:
    reader = PdfReader(uploaded_file)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_claims(text: str, client: anthropic.Anthropic) -> list[dict]:
    """Use Claude to pull out verifiable claims from the document."""
    prompt = f"""You are a claim extractor. From the document below, extract every specific, verifiable factual claim.
Focus on: statistics, percentages, dates, monetary figures, technical specs, named entities with attributed facts.
Ignore opinions and subjective statements.

For each claim return a JSON array of objects with these fields:
  "claim"      : the verbatim or near-verbatim claim from the document
  "category"   : one of [statistic, date, financial, technical, attribution]
  "search_query": a concise web search query to verify this claim (5-8 words max)

Respond ONLY with the raw JSON array — no explanation, no markdown fences.

DOCUMENT:
{text[:12000]}
"""
    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    # strip possible markdown fences
    raw = re.sub(r"^```json\s*|^```\s*|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except Exception:
        # fallback: try to extract any JSON array
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        return []


def web_search(query: str, max_results: int = 4) -> list[dict]:
    """DuckDuckGo search returning list of {title, href, body}."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return results
    except Exception:
        return []


def fetch_snippet(url: str, timeout: int = 5) -> str:
    """Fetch a short text snippet from a URL."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (FactCheckBot/1.0)"}
        r = requests.get(url, headers=headers, timeout=timeout)
        soup = BeautifulSoup(r.text, "html.parser")
        paragraphs = soup.find_all("p")
        text = " ".join(p.get_text() for p in paragraphs[:6])
        return text[:1500]
    except Exception:
        return ""


def verify_claim(claim_obj: dict, client: anthropic.Anthropic) -> dict:
    """Search the web and ask Claude to evaluate the claim."""
    query = claim_obj.get("search_query", claim_obj["claim"][:80])
    results = web_search(query, max_results=4)

    # build context from search results
    context_parts = []
    sources = []
    for r in results:
        snippet = r.get("body", "")
        if len(snippet) < 80:
            snippet = fetch_snippet(r.get("href", ""), timeout=4)
        context_parts.append(f"SOURCE: {r.get('href','')}\nTITLE: {r.get('title','')}\nSNIPPET: {snippet[:600]}")
        sources.append({"title": r.get("title", ""), "url": r.get("href", "")})

    context = "\n\n---\n\n".join(context_parts) if context_parts else "No search results found."

    prompt = f"""You are a rigorous fact-checker. Evaluate the claim below against the web evidence provided.

CLAIM: "{claim_obj['claim']}"

WEB EVIDENCE:
{context}

Based on the evidence, return a JSON object with these exact fields:
  "verdict"     : one of ["Verified", "Inaccurate", "False", "Unverified"]
  "confidence"  : integer 0-100
  "explanation" : 1-2 sentences explaining your verdict
  "correct_fact": if Inaccurate or False, state the best available correct fact; otherwise null

Verdict definitions:
  Verified   — evidence clearly supports the claim
  Inaccurate — claim is partly right but outdated or numerically off
  False      — evidence clearly contradicts the claim
  Unverified — insufficient evidence found

Respond ONLY with the raw JSON object — no markdown, no explanation outside JSON.
"""
    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```json\s*|^```\s*|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        result = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        result = json.loads(m.group()) if m else {}

    result["claim"] = claim_obj["claim"]
    result["category"] = claim_obj.get("category", "unknown")
    result["search_query"] = query
    result["sources"] = sources[:3]
    return result


def badge_html(verdict: str) -> str:
    cls = verdict.lower().replace(" ", "-")
    return f'<span class="badge badge-{cls}">{verdict}</span>'


def render_claim_card(r: dict):
    verdict = r.get("verdict", "Unverified")
    css = verdict.lower()
    icons = {"Verified": "✅", "Inaccurate": "⚠️", "False": "❌", "Unverified": "❓"}
    icon = icons.get(verdict, "❓")
    conf = r.get("confidence", 0)
    explanation = r.get("explanation", "")
    correct = r.get("correct_fact", "")
    sources = r.get("sources", [])
    cat = r.get("category", "").capitalize()

    source_links = " · ".join(
        f'<a href="{s["url"]}" target="_blank">{s["title"][:50] or s["url"][:40]}</a>'
        for s in sources if s.get("url")
    )

    correct_html = ""
    if correct:
        correct_html = f"<p style='color:#FDE68A;font-size:13px;margin-top:8px'>📌 <b>Correct fact:</b> {correct}</p>"

    src_html = ""
    if source_links:
        src_html = f"<div class='source-link' style='margin-top:8px;font-size:12px;color:#94A3B8'>🔗 Sources: {source_links}</div>"

    st.markdown(f"""
<div class="claim-card {css}">
  {badge_html(verdict)}
  <span style="font-size:11px;color:#64748B;margin-left:8px">{cat} · Confidence: {conf}%</span>
  <p style="font-size:14px;color:#CBD5E1;margin:6px 0 4px 0"><b>{icon} {r['claim']}</b></p>
  <p style="font-size:13px;color:#94A3B8;margin:0">{explanation}</p>
  {correct_html}
  {src_html}
</div>
""", unsafe_allow_html=True)


# ── Sidebar: API key ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    api_key = st.text_input("Anthropic API Key", type="password",
                            help="Your key stays in session memory only.")
    st.markdown("---")
    st.markdown("**How it works:**\n1. Upload PDF\n2. Claude extracts claims\n3. DuckDuckGo searches each claim\n4. Claude verdicts each claim\n5. Report shown")

# ── Main UI ───────────────────────────────────────────────────────────────────
uploaded = st.file_uploader("📄 Upload PDF for fact-checking", type=["pdf"])

if uploaded and api_key:
    if st.button("🚀 Start Fact-Check", type="primary", use_container_width=True):
        client = anthropic.Anthropic(api_key=api_key)

        with st.spinner("📄 Extracting text from PDF…"):
            text = extract_text_from_pdf(uploaded)
            word_count = len(text.split())
            st.info(f"Extracted {word_count:,} words from **{uploaded.name}**")

        with st.spinner("🧠 Identifying verifiable claims…"):
            claims = extract_claims(text, client)
            if not claims:
                st.error("No verifiable claims found. Try a document with specific statistics or factual assertions.")
                st.stop()
            st.success(f"Found **{len(claims)} verifiable claims** to check")

        # Verify each claim
        results = []
        progress = st.progress(0, text="Verifying claims against live web data…")
        status_col1, status_col2 = st.columns([3, 1])

        for i, claim_obj in enumerate(claims):
            with status_col1:
                st.caption(f"🔎 Checking: _{claim_obj['claim'][:90]}…_")
            result = verify_claim(claim_obj, client)
            results.append(result)
            progress.progress((i + 1) / len(claims), text=f"Verified {i+1}/{len(claims)} claims")
            time.sleep(0.3)  # rate-limit courtesy

        progress.empty()

        # ── Summary metrics ──
        st.divider()
        counts = {v: sum(1 for r in results if r.get("verdict") == v) for v in ["Verified", "Inaccurate", "False", "Unverified"]}
        c1, c2, c3, c4 = st.columns(4)
        for col, (label, color) in zip(
            [c1, c2, c3, c4],
            [("✅ Verified", "#10B981"), ("⚠️ Inaccurate", "#F59E0B"), ("❌ False", "#EF4444"), ("❓ Unverified", "#6B7280")]
        ):
            verdict_key = label.split(" ", 1)[1]
            col.markdown(f"""
<div class="metric-box">
  <div class="metric-num" style="color:{color}">{counts[verdict_key]}</div>
  <div style="color:#94A3B8;font-size:13px">{label}</div>
</div>""", unsafe_allow_html=True)

        # ── Filter ──
        st.divider()
        st.markdown("### 📋 Claim-by-Claim Results")
        filter_choice = st.radio("Filter by verdict:", ["All", "Verified", "Inaccurate", "False", "Unverified"], horizontal=True)

        filtered = results if filter_choice == "All" else [r for r in results if r.get("verdict") == filter_choice]
        for r in filtered:
            render_claim_card(r)

        # ── Download JSON ──
        st.divider()
        st.download_button(
            "⬇️ Download full report (JSON)",
            data=json.dumps(results, indent=2),
            file_name="factcheck_report.json",
            mime="application/json"
        )

elif uploaded and not api_key:
    st.warning("⬅️ Please enter your Anthropic API key in the sidebar to begin.")
elif not uploaded:
    st.markdown("""
<div style="text-align:center;padding:60px 20px;color:#475569">
  <div style="font-size:64px">📄</div>
  <h3 style="color:#94A3B8">Upload a PDF to begin</h3>
  <p>The agent will extract statistics, dates, and factual claims, then verify each one against live web data.</p>
</div>
""", unsafe_allow_html=True)