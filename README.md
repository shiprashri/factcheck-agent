# 🔍 Fact-Check Agent

A deployed web app that reads a PDF, extracts verifiable claims, cross-references them against live web data, and flags each claim as **Verified**, **Inaccurate**, or **False**.

## 🚀 Live Demo
> Deploy URL goes here (see Deployment section below)

## ✨ Features

| Feature | Detail |
|---------|--------|
| PDF Upload | Drag-and-drop any PDF |
| Claim Extraction | Claude identifies stats, dates, financial & technical figures |
| Live Web Verification | DuckDuckGo search + page scraping for each claim |
| Verdict Engine | Claude evaluates evidence → Verified / Inaccurate / False / Unverified |
| Correct Facts | For wrong claims, the real fact is surfaced |
| Source Links | Every verdict links to supporting web sources |
| Report Download | Full JSON report download |

## 🛠 Tech Stack

- **Frontend**: Streamlit
- **LLM**: Anthropic Claude (`claude-opus-4-5`)
- **PDF parsing**: PyMuPDF (fitz)
- **Web search**: DuckDuckGo Search (duckduckgo-search)
- **Scraping**: BeautifulSoup4 + requests
- **Deployment**: Streamlit Community Cloud

## 📦 Installation (Local)

```bash
git clone https://github.com/<your-username>/factcheck-agent
cd factcheck-agent
pip install -r requirements.txt
streamlit run app.py
```

Then open `http://localhost:8501` and enter your Anthropic API key in the sidebar.

## ☁️ Deployment (Streamlit Cloud)

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Click **New app** → select this repo → set main file to `app.py`
4. Click **Deploy**

Users supply their own Anthropic API key via the sidebar — no server-side secrets needed.

## 🧪 How to Test (Trap Document)

Upload any PDF containing made-up or outdated statistics. The agent will:
1. Extract each verifiable claim
2. Search the web for current data
3. Flag claims that don't match reality, and provide the correct figures

## 📂 File Structure

```
factcheck-agent/
├── app.py              # Main Streamlit application
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

## ⚙️ Environment

No environment variables required. Users enter their Anthropic API key directly in the app sidebar (stored only in the browser session).
# factcheck-agent
