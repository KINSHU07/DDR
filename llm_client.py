"""
llm_client.py — fixed for Groq free-tier 12,000 TPM limit
"""

import os
import json
import re
import time
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# ── Token budget constants ──────────────────────────────────────────────────
GROQ_FREE_TIER_LIMIT   = 12_000
SYSTEM_PROMPT_TOKENS   = 1_200
RESPONSE_RESERVE       = 4_000
IMAGE_INVENTORY_TOKENS = 400
CHARS_PER_TOKEN        = 4

AVAILABLE_TOKENS   = GROQ_FREE_TIER_LIMIT - SYSTEM_PROMPT_TOKENS - RESPONSE_RESERVE - IMAGE_INVENTORY_TOKENS
MAX_COMBINED_CHARS = AVAILABLE_TOKENS * CHARS_PER_TOKEN   # ~25,600 chars
MAX_CHARS_PER_DOC  = MAX_COMBINED_CHARS // 2              # ~12,800 chars each

# ── System prompt ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert property inspection analyst. Generate a structured DDR (Detailed Diagnostic Report) from two documents.

Documents provided:
1. Inspection Report — site observations, area descriptions, issue details
2. Thermal Report — temperature readings, thermal camera findings
3. Image Inventory — images extracted from both documents

Rules:
- Merge related findings from both docs (no duplicates)
- Mark conflicts as: "Conflict noted: [Inspection says X, Thermal says Y]"
- Mark missing info as: "Not Available"
- Use simple client-friendly language
- Do NOT invent facts not in the documents
- Only reference image IDs from the Image Inventory

Return ONLY a valid JSON object — no markdown, no code fences, no extra text:

{
  "property_issue_summary": {
    "overview": "2-4 sentence summary",
    "total_issues_found": 0,
    "critical_count": 0,
    "moderate_count": 0,
    "minor_count": 0
  },
  "area_wise_observations": [
    {
      "area_name": "Area name",
      "inspection_findings": "Inspection findings for this area",
      "thermal_findings": "Thermal findings or Not Available",
      "combined_summary": "Merged plain-language summary",
      "image_references": ["img_1"]
    }
  ],
  "probable_root_cause": [
    {
      "issue": "Issue name",
      "cause": "Root cause from evidence",
      "affected_areas": ["Area 1"]
    }
  ],
  "severity_assessment": [
    {
      "area_name": "Area name",
      "severity": "Critical",
      "reasoning": "Why this severity"
    }
  ],
  "recommended_actions": [
    {
      "priority": "Immediate",
      "area": "Area name",
      "action": "What to do",
      "estimated_urgency": "Within 48 hours"
    }
  ],
  "additional_notes": ["Note 1"],
  "missing_or_unclear_information": [
    {
      "field": "Expected field",
      "status": "Not Available",
      "detail": "Explanation"
    }
  ],
  "image_placement_map": [
    {
      "image_id": "img_1",
      "source_document": "Inspection Report",
      "description": "What this image shows",
      "place_in_section": "area_wise_observations",
      "place_in_area": "Area name"
    }
  ]
}

severity = Critical | Moderate | Minor  (exact, one of these only)
priority = Immediate | Short-term | Long-term  (exact, one of these only)
status   = Not Available | Unclear | Conflicting  (exact, one of these only)
Numbers must be integers. Empty lists = []. Return ONLY JSON.
"""

# ── Token helpers ────────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def smart_truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_page = truncated.rfind("\n[Page ")
    if last_page > max_chars * 0.6:
        truncated = truncated[:last_page]
    return truncated + (
        "\n\n[NOTE: Document truncated to fit AI token limits. "
        "Analyse only the content shown above.]"
    )


def fit_documents_to_budget(inspection_text: str, thermal_text: str):
    insp_limit  = MAX_CHARS_PER_DOC
    therm_limit = MAX_CHARS_PER_DOC

    insp_actual = len(inspection_text)
    if insp_actual < insp_limit:
        therm_limit += (insp_limit - insp_actual)

    therm_actual = len(thermal_text)
    if therm_actual < therm_limit:
        insp_limit += (therm_limit - therm_actual)

    insp_limit  = min(insp_limit,  MAX_COMBINED_CHARS)
    therm_limit = min(therm_limit, MAX_COMBINED_CHARS)

    return (
        smart_truncate(inspection_text, insp_limit),
        smart_truncate(thermal_text,    therm_limit),
    )

# ── Prompt builder ───────────────────────────────────────────────────────────

def build_user_prompt(inspection_text: str, thermal_text: str, image_inventory: str) -> str:
    return (
        "DOCUMENT 1: INSPECTION REPORT\n"
        "---\n"
        f"{inspection_text}\n\n"
        "DOCUMENT 2: THERMAL REPORT\n"
        "---\n"
        f"{thermal_text}\n\n"
        "IMAGE INVENTORY\n"
        "---\n"
        f"{image_inventory}\n\n"
        "Generate the DDR JSON now. Return only valid JSON."
    )

# ── JSON cleaner ─────────────────────────────────────────────────────────────

def clean_json_response(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"```(?:json)?", "", raw)
    raw = raw.strip()
    start = raw.find("{")
    end   = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start : end + 1]
    return raw.strip()

# ── Main entry point ─────────────────────────────────────────────────────────

def generate_ddr_json(
    inspection_text: str,
    thermal_text: str,
    image_inventory: str,
    model: str = "llama-3.3-70b-versatile",
    max_tokens: int = 4_000,
    max_retries: int = 3,
) -> dict:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to your .env file.\n"
            "Free key at: https://console.groq.com"
        )

    client = Groq(api_key=api_key)

    # Trim inputs to budget
    orig_insp  = len(inspection_text)
    orig_therm = len(thermal_text)
    inspection_text, thermal_text = fit_documents_to_budget(inspection_text, thermal_text)

    if len(inspection_text) < orig_insp:
        print(f"  Inspection truncated: {orig_insp:,} → {len(inspection_text):,} chars (~{estimate_tokens(inspection_text):,} tokens)")
    if len(thermal_text) < orig_therm:
        print(f"  Thermal truncated: {orig_therm:,} → {len(thermal_text):,} chars (~{estimate_tokens(thermal_text):,} tokens)")

    # Trim image inventory
    invent_cap = IMAGE_INVENTORY_TOKENS * CHARS_PER_TOKEN
    if len(image_inventory) > invent_cap:
        image_inventory = image_inventory[:invent_cap] + "\n[Inventory truncated]"

    user_prompt = build_user_prompt(inspection_text, thermal_text, image_inventory)
    est_tokens  = estimate_tokens(SYSTEM_PROMPT) + estimate_tokens(user_prompt)
    print(f"  Estimated tokens: ~{est_tokens:,} / {GROQ_FREE_TIER_LIMIT:,} limit")
    print(f"  Calling Groq ({model})...")

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.1,
            )
            raw     = response.choices[0].message.content
            cleaned = clean_json_response(raw)
            data    = json.loads(cleaned)
            print("  DDR JSON generated successfully.")
            return data

        except json.JSONDecodeError as e:
            last_error = e
            print(f"  Attempt {attempt}/{max_retries} — Bad JSON: {e}")

        except Exception as e:
            last_error = e
            err_str = str(e)
            print(f"  Attempt {attempt}/{max_retries} — API error: {err_str[:300]}")

            # If still 413, cut by 20% and retry immediately
            if "413" in err_str or "too large" in err_str.lower() or "rate_limit" in err_str.lower():
                print("  Still over limit — trimming inputs by 20%...")
                inspection_text = smart_truncate(inspection_text, int(len(inspection_text) * 0.8))
                thermal_text    = smart_truncate(thermal_text,    int(len(thermal_text)    * 0.8))
                user_prompt     = build_user_prompt(inspection_text, thermal_text, image_inventory)
                time.sleep(3)
                continue

        if attempt < max_retries:
            wait = 2 ** attempt
            print(f"  Retrying in {wait}s...")
            time.sleep(wait)

    raise ValueError(
        f"Failed after {max_retries} attempts. Last error: {last_error}\n\n"
        "Try one of:\n"
        "  1. Use fewer-page PDFs\n"
        "  2. Switch to 'mixtral-8x7b-32768' in the sidebar\n"
        "  3. Upgrade Groq: https://console.groq.com/settings/billing"
    )