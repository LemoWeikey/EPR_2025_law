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

# Load API key with validation
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("❌ WARNING: OPENAI_API_KEY not found!")
    client = None
else:
    print("✅ OpenAI API key loaded")
    client = OpenAI(api_key=api_key)

PDF_FOLDER = "uploads"
os.makedirs(PDF_FOLDER, exist_ok=True)

# ---------- Utility: Extract text (your original) ----------
def extract_pdf_text(pdf_path):
    text = ""
    try:
        print(f"🔍 Extracting text from: {pdf_path}")
        reader = PdfReader(pdf_path)
        print(f"📄 PDF has {len(reader.pages)} pages")
        
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        print(f"✅ Extracted {len(text)} characters with PyPDF2")
    except Exception as e:
        print(f"❌ PyPDF2 extraction failed: {e}")

    if not text.strip():
        print("⚠️ No text found, switching to OCR...")
        try:
            print("🖼️ Converting PDF to images...")
            images = convert_from_path(pdf_path)
            print(f"📸 Converted to {len(images)} images")
            
            for i, img in enumerate(images):
                print(f"🔤 Running OCR on image {i+1}...")
                ocr_text = pytesseract.image_to_string(img)
                text += ocr_text + "\n"
                print(f"✅ OCR extracted {len(ocr_text)} characters from image {i+1}")
                
        except Exception as e:
            print(f"❌ OCR failed: {e}")
            print(f"❌ Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()

    final_text = text.strip()
    print(f"📝 Final text length: {len(final_text)}")
    if final_text:
        print(f"📄 Preview: {final_text[:200]}...")
    return final_text

# ---------- Utility: Vision fallback (your original) ----------
def summarize_with_vision(pdf_path):
    print(f"👁️ Starting vision processing for: {pdf_path}")
    try:
        print("📷 Converting first page to image...")
        images = convert_from_path(pdf_path, first_page=1, last_page=1)
        print(f"✅ Converted {len(images)} images")
        
        print("🖼️ Encoding image to base64...")
        buffered = BytesIO()
        images[0].save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        print(f"✅ Base64 encoded, length: {len(img_str)}")

        print("🤖 Calling GPT-4o vision API...")
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Your original model
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
        result = response.choices[0].message.content
        print("✅ Vision API successful!")
        return result
    except Exception as e:
        print(f"❌ Vision API failed: {e}")
        print(f"❌ Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
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

@app.route("/debug", methods=["GET"])
def debug():
    """Debug system dependencies"""
    debug_info = {
        "openai_api_configured": bool(api_key),
        "pdf_folder_exists": os.path.exists(PDF_FOLDER),
        "uploads_contents": os.listdir(PDF_FOLDER) if os.path.exists(PDF_FOLDER) else []
    }
    
    # Test system dependencies
    try:
        import pdf2image
        debug_info["pdf2image_available"] = True
    except ImportError as e:
        debug_info["pdf2image_available"] = False
        debug_info["pdf2image_error"] = str(e)
    
    try:
        import pytesseract
        debug_info["pytesseract_available"] = True
        # Test tesseract executable
        pytesseract.get_tesseract_version()
        debug_info["tesseract_executable_works"] = True
    except Exception as e:
        debug_info["pytesseract_available"] = True
        debug_info["tesseract_executable_works"] = False
        debug_info["tesseract_error"] = str(e)
    
    # Test poppler (needed for pdf2image)
    try:
        import subprocess
        result = subprocess.run(['pdftoppm', '-h'], capture_output=True)
        debug_info["poppler_available"] = result.returncode == 0
    except Exception as e:
        debug_info["poppler_available"] = False
        debug_info["poppler_error"] = str(e)
    
    return jsonify(debug_info)

@app.route("/test-extraction/<filename>", methods=["GET"])
def test_extraction(filename):
    """Test each extraction method separately"""
    pdf_path = os.path.join(PDF_FOLDER, filename)
    if not os.path.exists(pdf_path):
        return jsonify({"error": f"File not found: {filename}"}), 404
    
    results = {"filename": filename}
    
    # Test PyPDF2
    try:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        results["pypdf2"] = {
            "success": True,
            "text_length": len(text.strip()),
            "preview": text.strip()[:200] if text.strip() else ""
        }
    except Exception as e:
        results["pypdf2"] = {"success": False, "error": str(e)}
    
    # Test pdf2image
    try:
        images = convert_from_path(pdf_path, first_page=1, last_page=1)
        results["pdf2image"] = {
            "success": True,
            "images_created": len(images),
            "image_size": images[0].size if images else None
        }
    except Exception as e:
        results["pdf2image"] = {"success": False, "error": str(e)}
    
    # Test pytesseract (only if pdf2image worked)
    if results.get("pdf2image", {}).get("success"):
        try:
            images = convert_from_path(pdf_path, first_page=1, last_page=1)
            ocr_text = pytesseract.image_to_string(images[0])
            results["pytesseract"] = {
                "success": True,
                "text_length": len(ocr_text.strip()),
                "preview": ocr_text.strip()[:200] if ocr_text.strip() else ""
            }
        except Exception as e:
            results["pytesseract"] = {"success": False, "error": str(e)}
    
    return jsonify(results)

@app.route("/chat", methods=["POST"])
def chat():
    """Generate AI summary for a PDF file - YOUR ORIGINAL LOGIC"""
    data = request.get_json()
    pdf_filename = data.get("pdf")

    if not pdf_filename:
        return jsonify({"error": "No PDF filename provided"}), 400

    pdf_path = os.path.join(PDF_FOLDER, pdf_filename)
    if not os.path.exists(pdf_path):
        return jsonify({"error": "File not found"}), 404

    if not client:
        return jsonify({"error": "OpenAI API key not configured"}), 500

    try:
        print(f"🚀 Processing: {pdf_filename}")
        
        # Step 1: Extract text (your original approach)
        text = extract_pdf_text(pdf_path)

        if text:
            # Summarize extracted text with GPT-3.5 (your original)
            try:
                print("🤖 Using GPT-3.5 for text summary...")
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {
                            "role": "system",
                            "content": "Bạn là một trợ lý AI hữu ích, luôn tóm tắt tài liệu bằng tiếng Việt, rõ ràng và dễ hiểu, sử dụng gạch đầu dòng."
                        },
                        {
                            "role": "user",
                            "content": f"Hãy tóm tắt tài liệu PDF này:\\n\\n{text}"
                        }
                    ],
                )
                answer = response.choices[0].message.content
                print("✅ GPT-3.5 summary completed")
                return jsonify({"answer": answer})
            except Exception as e:
                print(f"❌ GPT-3.5 failed: {e}")
                return jsonify({"error": f"LLM error: {str(e)}"}), 500
        else:
            # Step 2: Vision fallback with GPT-4o-mini (your original)
            print("🔄 Falling back to vision processing...")
            vision_summary = summarize_with_vision(pdf_path)
            if vision_summary:
                print("✅ Vision summary completed")
                return jsonify({"answer": vision_summary})
            else:
                return jsonify({"error": "Could not extract any text or summarize PDF"}), 500
                
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Processing error: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("🌱 EcoSummarize Server Starting...")
    print("📁 Upload folder:", PDF_FOLDER)
    print(f"🌐 Server: http://0.0.0.0:{port}")
    print(f"🤖 OpenAI configured: {'Yes' if client else 'No'}")
    
    app.run(host="0.0.0.0", port=port, debug=False)