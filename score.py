
# ============= score.py ============

import numpy as np

def embed(model_, text):
    """
    Embed the input text using the specified model.
    """
    return model_.encode(text, convert_to_tensor=True,show_progress_bar=False)

def resume_jd_similarity(resume_emb: str, jd_emb: str) -> float:

    # Compute cosine similarity
    cosine_sim = np.dot(resume_emb, jd_emb) / (np.linalg.norm(resume_emb) * np.linalg.norm(jd_emb))
    return round(float(cosine_sim), 4)

import PyPDF2

def extract_text_from_pdf(file_path: str) -> str:
    text = ""
    try:
        with open(file_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() or ""  # some pages may return None
        return text.strip()
    except Exception as e:
        print(f"Error extracting text from {file_path}: {e}")
        return ""
