from flask import Flask, request, jsonify, send_from_directory, render_template_string
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
app = Flask(__name__, static_folder='frontend', static_url_path='/static')
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
    try:
        # First try to serve from frontend folder
        return send_from_directory("frontend", "index.html")
    except:
        # Fallback: serve inline HTML if frontend folder doesn't exist
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>EcoSummarize</title>
            <meta charset="UTF-8">
        </head>
        <body>
            <h1>EcoSummarize - PDF AI Summary</h1>
            <div id="pdf-list"></div>
            <div id="summary-output"></div>
            
            <script>
                // Load PDF list
                fetch('/uploads')
                    .then(response => response.json())
                    .then(files => {
                        const listDiv = document.getElementById('pdf-list');
                        if (files.length > 0) {
                            listDiv.innerHTML = '<h2>Available PDFs:</h2><ul>' + 
                                files.map(f => `<li><a href="#" onclick="summarizePDF('${f.filename}')">${f.filename} (${f.size_mb} MB)</a></li>`).join('') + 
                                '</ul>';
                        } else {
                            listDiv.innerHTML = '<p>No PDF files found. Please upload some PDFs to the uploads folder.</p>';
                        }
                    })
                    .catch(err => {
                        document.getElementById('pdf-list').innerHTML = '<p>Error loading PDFs: ' + err + '</p>';
                        console.error('Error:', err);
                    });

                function summarizePDF(filename) {
                    document.getElementById('summary-output').innerHTML = '<p>Generating summary...</p>';
                    
                    fetch('/chat', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({pdf: filename})
                    })
                    .then(response => response.json())
                    .then(data => {
                        if (data.answer) {
                            document.getElementById('summary-output').innerHTML = 
                                '<h2>Summary for ' + filename + ':</h2><div>' + data.answer.replace(/\\n/g, '<br>') + '</div>';
                        } else {
                            document.getElementById('summary-output').innerHTML = '<p>Error: ' + data.error + '</p>';
                        }
                    })
                    .catch(err => {
                        document.getElementById('summary-output').innerHTML = '<p>Error: ' + err + '</p>';
                    });
                }
            </script>
        </body>
        </html>
        """)

@app.route("/uploads", methods=["GET"])
def list_pdfs():
    """List all PDF files in the uploads folder"""
    files = []
    try:
        # Check if uploads folder exists and create it if not
        if not os.path.exists(PDF_FOLDER):
            os.makedirs(PDF_FOLDER, exist_ok=True)
            
        print(f"Checking folder: {PDF_FOLDER}")
        print(f"Folder exists: {os.path.exists(PDF_FOLDER)}")
        
        if os.path.exists(PDF_FOLDER):
            folder_contents = os.listdir(PDF_FOLDER)
            print(f"Folder contents: {folder_contents}")
            
            for f in folder_contents:
                if f.lower().endswith(".pdf"):
                    file_path = os.path.join(PDF_FOLDER, f)
                    size_mb = round(os.path.getsize(file_path) / (1024 * 1024), 2)
                    files.append({"filename": f, "size_mb": size_mb})
                    print(f"Found PDF: {f}")
        
        print(f"Returning {len(files)} PDF files")
        return jsonify(files)
        
    except Exception as e:
        print(f"Error listing files: {str(e)}")
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
    """Debug route to check file system"""
    try:
        current_dir = os.getcwd()
        uploads_exists = os.path.exists(PDF_FOLDER)
        uploads_contents = []
        
        if uploads_exists:
            uploads_contents = os.listdir(PDF_FOLDER)
        
        return jsonify({
            "current_directory": current_dir,
            "uploads_folder_exists": uploads_exists,
            "uploads_path": os.path.abspath(PDF_FOLDER),
            "uploads_contents": uploads_contents,
            "all_files_in_current_dir": os.listdir(".")
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/chat", methods=["POST"])
def chat():
    """Generate AI summary for a PDF file"""
    data = request.get_json()
    pdf_filename = data.get("pdf")

    if not pdf_filename:
        return jsonify({"error": "No PDF filename provided"}), 400

    pdf_path = os.path.join(PDF_FOLDER, pdf_filename)
    if not os.path.exists(pdf_path):
        return jsonify({"error": f"File not found: {pdf_path}"}), 404

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
    
    # Debug info
    print(f"Current working directory: {os.getcwd()}")
    print(f"Uploads folder exists: {os.path.exists(PDF_FOLDER)}")
    if os.path.exists(PDF_FOLDER):
        print(f"Files in uploads: {os.listdir(PDF_FOLDER)}")
    
    app.run(host="0.0.0.0", port=port, debug=False)