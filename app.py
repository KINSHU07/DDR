"""
app.py — Streamlit UI for DDR Report Generator
Fixes: docx bytes read into memory before temp dir cleanup, token warning shown in UI.
"""

import streamlit as st
import os, sys, json, tempfile, shutil
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from pdf_parser import parse_documents
from llm_client import generate_ddr_json, MAX_COMBINED_CHARS, GROQ_FREE_TIER_LIMIT
from report_builder import build_ddr_report

st.set_page_config(page_title="DDR Report Generator", page_icon="🏠", layout="centered")

st.markdown("""
<style>
.main-title { font-size:2rem; font-weight:700; color:#1F4E79; margin-bottom:0; }
.subtitle   { color:#666; margin-top:4px; margin-bottom:24px; }
.step-box   { background:#F0F4F8; border-left:4px solid #378ADD; padding:12px 16px;
              border-radius:0 8px 8px 0; margin-bottom:12px; font-size:0.9rem; }
.badge-critical { color:#C00000; font-weight:bold; }
.badge-moderate { color:#C55A11; font-weight:bold; }
.badge-minor    { color:#1F7837; font-weight:bold; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">🏠 DDR Report Generator</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">AI-powered Detailed Diagnostic Report — Inspection + Thermal → Word document</div>', unsafe_allow_html=True)
st.divider()

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")

    groq_key = st.text_input("Groq API Key", type="password",
                              value=os.getenv("GROQ_API_KEY",""),
                              help="Free key at https://console.groq.com")
    if groq_key:
        os.environ["GROQ_API_KEY"] = groq_key

    model_choice = st.selectbox("Model", [
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "mixtral-8x7b-32768",
    ], index=0, help="llama-3.3-70b-versatile recommended")

    st.divider()

    st.info(
        f"**Free tier token limit:** {GROQ_FREE_TIER_LIMIT:,} TPM\n\n"
        f"**Max input per run:** ~{MAX_COMBINED_CHARS:,} chars combined.\n\n"
        "Large PDFs are automatically truncated to fit. No data is lost from extraction — "
        "only the portion sent to the AI is trimmed.",
        icon="ℹ️",
    )

    st.divider()
    st.markdown("**How it works**")
    st.markdown("""
    <div class="step-box">1. Upload both PDFs</div>
    <div class="step-box">2. Text + images extracted</div>
    <div class="step-box">3. Input trimmed to token budget</div>
    <div class="step-box">4. LLaMA generates DDR JSON</div>
    <div class="step-box">5. Word report built + downloaded</div>
    """, unsafe_allow_html=True)

    st.caption("Groq · LLaMA 3.3 · PyMuPDF · python-docx · Streamlit")

# ── File upload ──────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    st.subheader("📋 Inspection Report")
    inspection_file = st.file_uploader("inspection pdf", type=["pdf"], key="inspection",
                                        label_visibility="collapsed")
    if inspection_file:
        st.success(f"✓ {inspection_file.name}")

with col2:
    st.subheader("🌡️ Thermal Report")
    thermal_file = st.file_uploader("thermal pdf", type=["pdf"], key="thermal",
                                     label_visibility="collapsed")
    if thermal_file:
        st.success(f"✓ {thermal_file.name}")

st.divider()

if not os.getenv("GROQ_API_KEY"):
    st.warning("⚠️ Enter your Groq API key in the sidebar to continue.")

ready      = inspection_file and thermal_file and os.getenv("GROQ_API_KEY")
gen_button = st.button("🚀 Generate DDR Report", disabled=not ready,
                        use_container_width=True, type="primary")

if gen_button and ready:
    work_dir    = None
    docx_bytes  = None
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        work_dir  = tempfile.mkdtemp()
        imgs_dir  = os.path.join(work_dir, "images")
        out_dir   = os.path.join(work_dir, "output")
        os.makedirs(imgs_dir, exist_ok=True)
        os.makedirs(out_dir,  exist_ok=True)

        insp_path  = os.path.join(work_dir, "inspection.pdf")
        therm_path = os.path.join(work_dir, "thermal.pdf")
        with open(insp_path,  "wb") as f: f.write(inspection_file.read())
        with open(therm_path, "wb") as f: f.write(thermal_file.read())

        # Step 1 ── Parse PDFs
        with st.status("📄 Extracting content from PDFs...", expanded=True) as s:
            st.write("Reading Inspection Report...")
            st.write("Reading Thermal Report...")
            st.write("Extracting embedded images...")
            parsed = parse_documents(insp_path, therm_path, imgs_dir)
            st.write(f"✓ Text extracted — {len(parsed['inspection_text']):,} + {len(parsed['thermal_text']):,} chars")
            st.write(f"✓ {len(parsed['image_records'])} images found")
            s.update(label="✅ PDFs parsed", state="complete")

        # Token warning
        total_chars = len(parsed["inspection_text"]) + len(parsed["thermal_text"])
        if total_chars > MAX_COMBINED_CHARS:
            st.warning(
                f"⚠️ Combined document text ({total_chars:,} chars) exceeds the free-tier budget "
                f"({MAX_COMBINED_CHARS:,} chars). The input will be automatically trimmed — "
                "later pages may not be included in the AI analysis."
            )

        # Step 2 ── Generate DDR
        with st.status(f"🤖 Generating DDR with {model_choice}...", expanded=True) as s:
            st.write("Trimming input to token budget...")
            st.write("Calling LLaMA via Groq...")
            st.write("Structuring all 7 DDR sections...")
            ddr_data = generate_ddr_json(
                parsed["inspection_text"], parsed["thermal_text"],
                parsed["image_inventory"], model=model_choice,
            )
            total = ddr_data.get("property_issue_summary", {}).get("total_issues_found", 0)
            st.write(f"✓ {total} issues identified across all areas")
            s.update(label="✅ DDR content generated", state="complete")

        # Step 3 ── Build .docx
        with st.status("📝 Building Word document...", expanded=True) as s:
            st.write("Writing all 7 sections...")
            st.write("Embedding images...")
            out_path = os.path.join(out_dir, f"DDR_Report_{timestamp}.docx")
            build_ddr_report(ddr_data, parsed["image_records"], out_path)
            # Read bytes into memory BEFORE temp dir is deleted
            with open(out_path, "rb") as f:
                docx_bytes = f.read()
            s.update(label="✅ Report ready", state="complete")

        # Results dashboard
        st.success("🎉 DDR Report generated successfully!")
        st.divider()
        summary = ddr_data.get("property_issue_summary", {})
        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Total Issues",   summary.get("total_issues_found", 0))
        m2.metric("🔴 Critical",    summary.get("critical_count",     0))
        m3.metric("🟠 Moderate",    summary.get("moderate_count",     0))
        m4.metric("🟢 Minor",       summary.get("minor_count",        0))
        st.markdown(f"**Overview:** {summary.get('overview','')}")

        areas = ddr_data.get("area_wise_observations", [])
        if areas:
            st.subheader(f"📍 Areas Covered ({len(areas)})")
            for a in areas:
                st.markdown(f"- {a.get('area_name','')}")

        severity = ddr_data.get("severity_assessment", [])
        if severity:
            st.subheader("⚠️ Severity Breakdown")
            for s in severity:
                sev = s.get("severity","Minor")
                st.markdown(
                    f'**{s.get("area_name","")}** — <span class="badge-{sev.lower()}">{sev}</span>',
                    unsafe_allow_html=True,
                )
                st.caption(s.get("reasoning",""))

        missing = ddr_data.get("missing_or_unclear_information", [])
        if missing:
            with st.expander(f"⚠️ Missing / Unclear ({len(missing)} items)"):
                for m in missing:
                    st.markdown(f"- **{m.get('field','')}** ({m.get('status','')}): {m.get('detail','')}")

        st.divider()
        st.download_button(
            label="⬇️ Download DDR Report (.docx)",
            data=docx_bytes,
            file_name=f"DDR_Report_{timestamp}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True, type="primary",
        )

        with st.expander("🔍 Raw DDR JSON"):
            st.json(ddr_data)

    except ValueError as e:
        st.error(f"❌ {e}")
    except Exception as e:
        st.error(f"❌ Unexpected error: {e}")
        st.exception(e)
    finally:
        if work_dir and os.path.exists(work_dir):
            try:
                shutil.rmtree(work_dir)
            except Exception:
                pass

st.divider()
st.caption("DDR Report Generator · Groq + LLaMA 3.3 · python-docx · PyMuPDF · Streamlit")