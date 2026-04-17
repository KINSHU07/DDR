"""
pdf_parser.py — Python 3.8 compatible, with skip-logging for tiny images.
"""

import fitz
import os
from PIL import Image
import io
from typing import List, Dict


def extract_text_from_pdf(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    full_text = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()
        if text:
            full_text.append(f"[Page {page_num + 1}]\n{text}")
    doc.close()
    return "\n\n".join(full_text)


def extract_images_from_pdf(pdf_path: str, source_label: str, output_dir: str) -> List[Dict]:
    doc = fitz.open(pdf_path)
    image_records = []
    image_counter = 0
    os.makedirs(output_dir, exist_ok=True)

    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)
        nearby_text = page.get_text("text").strip()[:300].replace("\n", " ")

        for img_info in image_list:
            xref = img_info[0]
            try:
                base_image  = doc.extract_image(xref)
                image_bytes = base_image["image"]
                pil_image   = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                width, height = pil_image.size

                if width < 50 or height < 50:
                    print(f"  Skipping tiny image p{page_num+1} ({width}x{height}px)")
                    continue

                image_counter += 1
                image_id = f"img_{image_counter}"
                filename = f"{image_id}_{source_label.replace(' ', '_')}_p{page_num+1}.png"
                save_path = os.path.join(output_dir, filename)
                pil_image.save(save_path, "PNG")

                image_records.append({
                    "image_id":        image_id,
                    "file_path":       save_path,
                    "filename":        filename,
                    "source_document": source_label,
                    "page":            page_num + 1,
                    "width":           width,
                    "height":          height,
                    "nearby_text":     nearby_text or "No surrounding text found",
                })
            except Exception as e:
                print(f"  Warning: Could not extract image on page {page_num+1}: {e}")

    doc.close()
    return image_records


def build_image_inventory(image_records: List[Dict]) -> str:
    if not image_records:
        return "No images found in either document."
    lines = []
    for rec in image_records:
        lines.append(
            f"{rec['image_id']}: Source='{rec['source_document']}', "
            f"Page={rec['page']}, Size={rec['width']}x{rec['height']}px, "
            f"Nearby text: \"{rec['nearby_text'][:200]}\""
        )
    return "\n".join(lines)


def parse_documents(inspection_pdf_path: str, thermal_pdf_path: str, output_dir: str) -> Dict:
    print("Extracting text from Inspection Report...")
    inspection_text = extract_text_from_pdf(inspection_pdf_path)

    print("Extracting text from Thermal Report...")
    thermal_text = extract_text_from_pdf(thermal_pdf_path)

    print("Extracting images from Inspection Report...")
    inspection_images = extract_images_from_pdf(inspection_pdf_path, "Inspection Report", output_dir)

    print("Extracting images from Thermal Report...")
    thermal_images = extract_images_from_pdf(thermal_pdf_path, "Thermal Report", output_dir)

    all_images = inspection_images + thermal_images
    print(f"Extracted {len(inspection_images)} inspection + {len(thermal_images)} thermal images.")

    return {
        "inspection_text": inspection_text,
        "thermal_text":    thermal_text,
        "image_records":   all_images,
        "image_inventory": build_image_inventory(all_images),
    }