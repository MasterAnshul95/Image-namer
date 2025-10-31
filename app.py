import os
import cv2
import numpy as np
from flask import Flask, render_template, request, send_file, jsonify
from flask_cors import CORS  
from werkzeug.utils import secure_filename
from io import BytesIO
import zipfile
import uuid
import json
from datetime import datetime

import easyocr

app = Flask(__name__)
CORS(app)  
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
temp_dir = 'static/temp'
os.makedirs(temp_dir, exist_ok=True)
db_file = 'brand_visual_db.json'

# Initialize EasyOCR
reader = easyocr.Reader(['en'])


def load_db():
    """Load database from JSON file"""
    if os.path.exists(db_file):
        with open(db_file, 'r') as f:
            return json.load(f)
    return []


def save_db(data):
    """Save database to JSON file"""
    with open(db_file, 'w') as f:
        json.dump(data, f, indent=2)


def extract_main_text(image_path):
    """Extract the text with largest font size visually (by bounding box height)."""
    try:
        results = reader.readtext(image_path)
        if not results:
            return "No text detected"

        largest = max(results, key=lambda x: abs(x[0][0][1] - x[0][3][1]))
        text = largest[1].strip()
        return text
    except Exception as e:
        print("❌ OCR Error:", e)
        return "OCR failed"


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/brand-visual')
def brand_visual():
    return render_template('brand_visual.html')


@app.route('/upload', methods=['POST'])
def upload():
    try:
        mode = request.form.get('mode', 'single')
        if mode == 'bulk':
            files = request.files.getlist('images')
        else:
            file = request.files.get('image')
            files = [file] if file and file.filename != '' else []

        if not files:
            return jsonify({'error': 'No image uploaded'}), 400

        if mode == 'single' and len(files) != 1:
            return jsonify({'error': 'Single mode requires exactly one image'}), 400

        results = []
        for file in files:
            filename = secure_filename(file.filename)
            if not filename:
                continue
            unique_id = str(uuid.uuid4())
            name, ext = os.path.splitext(filename)
            temp_path = os.path.join(temp_dir, f"{unique_id}{ext}")
            file.save(temp_path)
            img = cv2.imread(temp_path)
            if img is None:
                os.remove(temp_path)
                continue
            text = extract_main_text(temp_path)
            results.append({
                'id': unique_id,
                'text': text,
                'preview': temp_path.replace(os.sep, '/'),
                'ext': ext
            })

        if not results:
            return jsonify({'error': 'No valid images processed'}), 400

        return jsonify({'mode': mode, 'results': results})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Internal Server Error: {str(e)}'}), 500


@app.route('/upload_brand_slides', methods=['POST'])
def upload_brand_slides():
    """Upload slides for brand visual - Extract OCR text from each image"""
    try:
        files = request.files.getlist('slides')
        if not files:
            return jsonify({'error': 'No images uploaded'}), 400

        results = []
        for file in files:
            filename = secure_filename(file.filename)
            if not filename:
                continue
            unique_id = str(uuid.uuid4())
            name, ext = os.path.splitext(filename)
            temp_path = os.path.join(temp_dir, f"{unique_id}{ext}")
            file.save(temp_path)
            img = cv2.imread(temp_path)
            if img is None:
                os.remove(temp_path)
                continue
            # Extract text using OCR
            text = extract_main_text(temp_path)
            results.append({
                'id': unique_id,
                'text': text,
                'preview': temp_path.replace(os.sep, '/'),
                'ext': ext,
                'filename': filename
            })

        if not results:
            return jsonify({'error': 'No valid images processed'}), 400

        return jsonify({'results': results})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Internal Server Error: {str(e)}'}), 500


@app.route('/save_brand_visual', methods=['POST'])
def save_brand_visual():
    """Save brand visual data using OCR extracted text as filename"""
    try:
        data = request.get_json()
        brand_name = data.get('brandName', '').strip()
        slides = data.get('slides', [])
        sequence = data.get('sequence', 1)
        
        if not brand_name or not slides:
            return jsonify({'error': 'Brand name and slides are required'}), 400

        print("\n" + "="*60)
        print("🔥 BRAND VISUAL SAVE REQUEST")
        print("="*60)
        print(f"📌 Brand Name: {brand_name}")
        print(f"📌 Sequence of Slide: {sequence}")
        print(f"📌 Total Slides: {len(slides)}")
        print("-"*60)

        # Load existing database
        db = load_db()
        
        # Create entry
        entry_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        # Process and save images using OCR text as filename
        saved_images = []
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for idx, slide in enumerate(slides):
                slide_id = slide['id']
                slide_text = slide['text'].strip()
                ext = slide['ext']
                temp_path = os.path.join(temp_dir, f"{slide_id}{ext}")
                
                if not os.path.exists(temp_path):
                    continue
                
                img = cv2.imread(temp_path)
                if img is None:
                    os.remove(temp_path)
                    continue
                
                # Use OCR extracted text as filename (your original logic)
                safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in slide_text)
                if not safe_name:
                    safe_name = 'unnamed'
                
                final_filename = f"{safe_name}.png"
                final_path = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)
                
                # Handle duplicate filenames
                base_name = safe_name
                counter = 1
                while os.path.exists(final_path):
                    final_filename = f"{base_name}_{counter}.png"
                    final_path = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)
                    counter += 1
                
                # Save image
                success = cv2.imwrite(final_path, img, [cv2.IMWRITE_PNG_COMPRESSION, 0])
                
                if success:
                    # Add to zip
                    encoded_success, encoded_img = cv2.imencode('.png', img, [cv2.IMWRITE_PNG_COMPRESSION, 0])
                    if encoded_success:
                        zip_file.writestr(final_filename, encoded_img.tobytes())
                    
                    saved_images.append({
                        'filename': final_filename,
                        'ocr_text': slide_text,
                        'path': final_path.replace(os.sep, '/'),
                        'order': idx + 1
                    })
                    
                    print(f"✅ Slide {idx + 1}:")
                    print(f"   - OCR Text: {slide_text}")
                    print(f"   - Saved As: {final_filename}")
                    print(f"   - Path: {final_path}")
                
                # Clean up temp file
                os.remove(temp_path)
        
        # Save to database
        db_entry = {
            'id': entry_id,
            'brand_name': brand_name,
            'sequence': sequence,
            'images': saved_images,
            'created_at': timestamp
        }
        db.append(db_entry)
        save_db(db)
        
        print("-"*60)
        print(f"💾 Saved to Database:")
        print(f"   - Entry ID: {entry_id}")
        print(f"   - Total Files Saved: {len(saved_images)}")
        print(f"   - Timestamp: {timestamp}")
        print("="*60 + "\n")
        
        # Prepare zip for download
        zip_buffer.seek(0)
        zip_filename = f"brand_visual_slides.zip"
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Internal Server Error: {str(e)}'}), 500


@app.route('/get_brand_visuals', methods=['GET'])
def get_brand_visuals():
    """Get all brand visual data"""
    try:
        db = load_db()
        return jsonify(db)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/confirm_single', methods=['POST'])
def confirm_single():
    try:
        data = request.get_json()
        id_ = data['id']
        text = data['text'].strip()
        ext = data['ext']
        temp_path = os.path.join(temp_dir, f"{id_}{ext}")
        if not os.path.exists(temp_path):
            return jsonify({'error': 'Temp file not found'}), 404
        img = cv2.imread(temp_path)
        if img is None:
            os.remove(temp_path)
            return jsonify({'error': 'Failed to process image'}), 500
        safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in text)
        if not safe_name:
            safe_name = 'unnamed'
        final_filename = f"{safe_name}.png"
        final_path = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)
        base_name = safe_name
        counter = 1
        while os.path.exists(final_path):
            final_filename = f"{base_name}_{counter}.png"
            final_path = os.path.join(app.config['UPLOAD_FOLDER'], final_filename)
            counter += 1
        success = cv2.imwrite(final_path, img, [cv2.IMWRITE_PNG_COMPRESSION, 0])
        if not success:
            os.remove(temp_path)
            return jsonify({'error': 'Failed to save image'}), 500
        os.remove(temp_path)
        return jsonify({'download_link': f"/download/{final_filename}"})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Internal Server Error: {str(e)}'}), 500


@app.route('/confirm_bulk', methods=['POST'])
def confirm_bulk():
    try:
        data = request.get_json()
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for item in data:
                id_ = item['id']
                text = item['text'].strip()
                ext = item['ext']
                temp_path = os.path.join(temp_dir, f"{id_}{ext}")
                if not os.path.exists(temp_path):
                    continue
                img = cv2.imread(temp_path)
                if img is None:
                    os.remove(temp_path)
                    continue
                success, encoded_img = cv2.imencode('.png', img, [cv2.IMWRITE_PNG_COMPRESSION, 0])
                if not success:
                    os.remove(temp_path)
                    continue
                safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in text)
                if not safe_name:
                    safe_name = 'unnamed'
                zip_filename = f"{safe_name}.png"
                counter = 1
                base_name = safe_name
                while zip_filename in [f for f in zip_file.namelist()]:
                    zip_filename = f"{base_name}_{counter}.png"
                    counter += 1
                zip_file.writestr(zip_filename, encoded_img.tobytes())
                os.remove(temp_path)
        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='extracted_images.zip'
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Internal Server Error: {str(e)}'}), 500


@app.route('/download/<filename>')
def download_file(filename):
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(path):
        return "File not found", 404
    return send_file(path, as_attachment=True)


if __name__ == '__main__':
    app.run(debug=True)