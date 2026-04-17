# DDR Report Generator

AI-powered Detailed Diagnostic Report generator. Upload an Inspection PDF and a Thermal PDF — get a structured, client-ready `.docx` report in seconds.

**Stack:** Python · Groq API · LLaMA 3.3 70B · PyMuPDF · python-docx · Streamlit

---

## Quick Start

### 1. Clone / Download the project
```bash
cd ddr-report-generator
```

### 2. Create a virtual environment
```bash
python -m venv venv

# Activate on Mac/Linux:
source venv/bin/activate

# Activate on Windows:
venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Get a free Groq API key
1. Go to [https://console.groq.com](https://console.groq.com)
2. Sign up (free)
3. Create an API key

### 5. Set up your environment
```bash
cp .env.example .env
```
Open `.env` and paste your key:
```
GROQ_API_KEY=gsk_your_actual_key_here
```

### 6. Run the Streamlit app
```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Usage

### Option A — Web UI (Streamlit)
1. Run `streamlit run app.py`
2. Enter your Groq API key in the sidebar
3. Upload Inspection PDF and Thermal PDF
4. Click **Generate DDR Report**
5. Download the `.docx` file

### Option B — Command Line
```bash
python run.py \
  --inspection path/to/inspection.pdf \
  --thermal path/to/thermal.pdf \
  --output ./output
```

---

## Project Structure
```
ddr-report-generator/
├── app.py                  # Streamlit UI
├── run.py                  # CLI runner
├── requirements.txt
├── .env.example
├── src/
│   ├── pdf_parser.py       # PDF text + image extraction (PyMuPDF)
│   ├── llm_client.py       # Groq API + prompt (LLaMA 3.3 70B)
│   └── report_builder.py   # .docx generation (python-docx)
└── output/                 # Generated reports saved here
```

---

## DDR Output Sections
1. Property Issue Summary
2. Area-wise Observations (with images)
3. Probable Root Cause
4. Severity Assessment (Critical / Moderate / Minor)
5. Recommended Actions (Immediate / Short-term / Long-term)
6. Additional Notes
7. Missing or Unclear Information

---

## Deploying to Streamlit Cloud (for live demo link)
1. Push this project to a GitHub repo
2. Go to [https://share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo
4. Set `GROQ_API_KEY` in Streamlit Cloud secrets
5. Deploy — you'll get a public URL instantly

---

## Models Available (Groq)
| Model | Speed | Context |
|---|---|---|
| `llama-3.3-70b-versatile` | Fast | 128K tokens |
| `llama-3.1-70b-versatile` | Fast | 128K tokens |
| `mixtral-8x7b-32768` | Very fast | 32K tokens |

`llama-3.3-70b-versatile` is recommended for best accuracy on structured JSON output.

---

## Limitations
- Image placement is based on nearby text context — may not be 100% accurate for unlabelled images
- Very large PDFs (100+ pages) may hit token limits; use `mixtral-8x7b-32768` for shorter context
- Groq free tier has rate limits (~30 req/min)