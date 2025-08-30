from flask import Flask, request, jsonify, send_from_directory
import os
from openai import OpenAI
from PyPDF2 import PdfReader
from dotenv import load_dotenv
from pdf2image import convert_from_path
import pytesseract
import base64
from io import BytesIO
from flask_cors import CORS

load_dotenv()
app = Flask(__name__)
CORS(app)

# Load API key
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PDF_FOLDER = "uploads"
os.makedirs(PDF_FOLDER, exist_ok=True)

# ---------- Utility: Extract text ----------
def extract_pdf_text(pdf_path):
    text = ""
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    except Exception as e:
        print("PyPDF2 extraction failed:", e)

    if not text.strip():
        print("⚠️ No text found, switching to OCR...")
        try:
            images = convert_from_path(pdf_path)
            for img in images:
                text += pytesseract.image_to_string(img) + "\n"
        except Exception as e:
            print("OCR failed:", e)

    return text.strip()

# ---------- Utility: Vision fallback ----------
def summarize_with_vision(pdf_path):
    try:
        images = convert_from_path(pdf_path, first_page=1, last_page=1)  # first page only
        buffered = BytesIO()
        images[0].save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

        response = client.chat.completions.create(
            model="gpt-4o-mini",  # must be GPT-4o family for images
            messages=[
                {
                    "role": "system",
                    "content": "Bạn là một trợ lý AI hữu ích, luôn tóm tắt tài liệu bằng tiếng Việt, rõ ràng và dễ hiểu, sử dụng gạch đầu dòng."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Hãy tóm tắt trang PDF này bằng tiếng Việt, dùng gạch đầu dòng."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_str}"}}
                    ],
                },
            ],
        )
        return response.choices[0].message.content
    except Exception as e:
        print("Vision API failed:", e)
        return None

# ---------- Routes ----------
@app.route("/", methods=["GET"])
def index():
    """Serve the main HTML page"""
    return send_from_directory("frontend", "index.html")


@app.route("/uploads", methods=["GET"])
def list_pdfs():
    """List all PDF files in the uploads folder"""
    files = []
    try:
        for f in os.listdir(PDF_FOLDER):
            if f.endswith(".pdf"):
                size_mb = round(os.path.getsize(os.path.join(PDF_FOLDER, f)) / (1024 * 1024), 2)
                files.append({"filename": f, "size_mb": size_mb})
        return jsonify(files)
    except Exception as e:
        return jsonify({"error": f"Could not list files: {str(e)}"}), 500

@app.route("/uploads/<filename>", methods=["GET"])
def serve_pdf(filename):
    """Serve a specific PDF file"""
    try:
        return send_from_directory(PDF_FOLDER, filename)
    except Exception as e:
        return jsonify({"error": "File not found"}), 404

@app.route("/chat", methods=["POST"])
def chat():
    """Generate AI summary for a PDF file"""
    data = request.get_json()
    pdf_filename = data.get("pdf")

    if not pdf_filename:
        return jsonify({"error": "No PDF filename provided"}), 400

    pdf_path = os.path.join(PDF_FOLDER, pdf_filename)
    if not os.path.exists(pdf_path):
        return jsonify({"error": "File not found"}), 404

    try:
        # Step 1: Extract text
        text = extract_pdf_text(pdf_path)

        if text:
            # Summarize extracted text with GPT-3.5
            try:
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {
                            "role": "system",
                            "content": "Bạn là một trợ lý AI hữu ích, luôn tóm tắt tài liệu bằng tiếng Việt, rõ ràng và dễ hiểu, sử dụng gạch đầu dòng."
                        },
                        {
                            "role": "user",
                            "content": f"Hãy tóm tắt tài liệu PDF này:\n\n{text}"
                        }
                    ],
                )
                answer = response.choices[0].message.content
                return jsonify({"answer": answer})
            except Exception as e:
                return jsonify({"error": f"LLM error: {str(e)}"}), 500
        else:
            # Step 2: Vision fallback with GPT-4o-mini
            vision_summary = summarize_with_vision(pdf_path)
            if vision_summary:
                return jsonify({"answer": vision_summary})
            else:
                return jsonify({"error": "Could not extract any text or summarize PDF"}), 500
                
    except Exception as e:
        return jsonify({"error": f"Processing error: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("🌱 EcoSummarize Server Starting...")
    print("📁 Upload folder:", PDF_FOLDER)
    print(f"🌐 Server: http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)