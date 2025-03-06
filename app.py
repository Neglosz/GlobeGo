from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_mail import Mail, Message
import google.generativeai as genai
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
import json
import re
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from PIL import Image, ExifTags
import uuid
import glob

load_dotenv()



app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key')  # เปลี่ยนเป็น secret key ที่ปลอดภัย


WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
# การกำหนดค่า Flask-Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'  # ใช้ SMTP ของ Gmail
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')  # อีเมลของคุณ
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')  # App Password จาก Gmail
mail = Mail(app)

# ตั้งค่า URLSafeTimedSerializer สำหรับโทเค็น
s = URLSafeTimedSerializer(app.secret_key)

# การกำหนดค่าโฟลเดอร์เก็บภาพ
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'static/images')  # โฟลเดอร์เก็บภาพ
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])  # สร้างโฟลเดอร์หากยังไม่มี


MONGO_URI = os.getenv('MONGO_URI')
gemini_api = os.getenv('GEMINI_API')
# สร้างการเชื่อมต่อกับ MongoDB Atlas
client = MongoClient(MONGO_URI)
db = client.get_database('user_appdev')  # เปลี่ยน <dbname> เป็นชื่อฐานข้อมูลที่ต้องการใช้งาน
users_collection = db.users  # สมมุติว่ามี collection สำหรับเก็บข้อมูลผู้ใช้

# ตั้งค่า API Key สำหรับ Gemini
genai.configure(api_key=gemini_api)

# ฟังก์ชันส่งอีเมลรีเซ็ต
def send_reset_email(email, token):
    reset_link = url_for('reset_password', token=token, _external=True)
    msg = Message('Reset Your Password', sender=app.config['MAIL_USERNAME'], recipients=[email])
    msg.body = f'คลิกที่นี่เพื่อรีเซ็ตรหัสผ่านของคุณ: {reset_link}\nลิงก์นี้จะหมดอายุใน 30 นาที'
    mail.send(msg)

# ฟังก์ชันตรวจสอบประเภทไฟล์
def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ฟังก์ชันปรับขนาดภาพ
def resize_image(file, email, target_size=(512, 512)):
    img = Image.open(file)
    # 🔄 ตรวจสอบและหมุนภาพตามค่า EXIF
    try:
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == "Orientation":
                break
        exif = img._getexif()

        if exif is not None and orientation in exif:
            if exif[orientation] == 3:
                img = img.rotate(180, expand=True)
            elif exif[orientation] == 6:
                img = img.rotate(270, expand=True)  # หมุนขวา 90 องศา
            elif exif[orientation] == 8:
                img = img.rotate(90, expand=True)   # หมุนซ้าย 90 องศา
    except (AttributeError, KeyError, IndexError):
        pass  # ถ้าไม่มี EXIF ก็ข้ามไป

    img = img.convert('RGB')
    img.thumbnail(target_size, Image.Resampling.LANCZOS)

    # กำหนดโฟลเดอร์ของผู้ใช้
    user_folder = os.path.join(app.config['UPLOAD_FOLDER'], email)
    if not os.path.exists(user_folder):
        os.makedirs(user_folder)

    existing_images = sorted(glob.glob(os.path.join(user_folder, "*.jpg")), key=os.path.getatime)
    if len(existing_images) >= 2:
        os.remove(existing_images[0])

    unique_filename = f"{uuid.uuid4().hex}.jpg"
    resized_path = os.path.join(user_folder, unique_filename)
    
    img.save(resized_path, optimize=True, quality=95)

    return f"{email}/{unique_filename}"

# ปรับฟังก์ชัน generate_trips ให้ใช้ location
def generate_trips(province, date, location=None):
    model = genai.GenerativeModel('gemini-pro')
    prompt = f"สร้างทริปการเดินทาง 3 ทริปที่ไม่ซ้ำกันสำหรับจังหวัด {province} ในวันที่ {date}"
    
    if location:
        prompt += f" โดยคำนึงถึงตำแหน่งปัจจุบันที่อยู่ใกล้กับ {location}"

    prompt += """
    พร้อมชื่อทริปสั้นๆ โดยระบุเวลาที่เป็นไปตามความจริงที่สุด และกิจกรรมอย่างละเอียด ถ้าที่เที่ยวในวันนั้นน้อยกว่า2ที่ให้เพิ่มวันได้ ย้ำว่ามีเวลากำกับด้วย และถ้ามีคำแนะนำก็สามารถใส่เข้ามาได้
    ตอบกลับในรูปแบบ JSON เท่านั้น ห้ามมีอักษรพิเศษ เช่น ``` หรือตัวอักษรนอก JSON:
    {
        "trips": [
            {
                "title": "ชื่อทริป",
                "activities": [
                    {"time": "08:00", "activity": "กิจกรรมที่ 1", "location": "สถานที่ 1"},
                    {"time": "10:00", "activity": "กิจกรรมที่ 2", "location": "สถานที่ 2"}
                ]
            }
        ]
    }
    """

    response = model.generate_content(prompt)
    raw_response = response.text.strip()
    print("Raw Response:", raw_response)  # ✅ ตรวจสอบค่า API Response
    # ✅ ใช้ Regular Expression เพื่อลบ {{ }} ที่อาจเกิดขึ้น
    cleaned_response = re.sub(r'{{\s*', '{', raw_response)
    cleaned_response = re.sub(r'\s*}}', '}', cleaned_response)
    print("cleaned_response:", cleaned_response)  # ✅ ตรวจสอบค่า API Response

    try:
        trips_data = json.loads(cleaned_response)  # ✅ แปลง JSON ที่สะอาดแล้ว
        if "trips" not in trips_data:
            raise ValueError("Invalid JSON format: 'trips' key not found")  # ถ้า JSON ไม่มี "trips" ให้ถือว่าผิดพลาด

        # ✅ แปลง "activities" ให้เป็นข้อความ
        for trip in trips_data.get("trips", []):
            trip["activities"] = [
                f"{act['time']} - {act['activity']} ({act['location']})"
                for act in trip.get("activities", [])
            ]

    except (json.JSONDecodeError, ValueError) as e:
        print("❌ JSON Decode Failed:", e)  # แจ้งเตือนว่ามีปัญหา
        trips_data = {"trips": []}

    return trips_data["trips"]

@app.route('/')
def index():
    if 'user' in session:
        # สมมุติว่ามีไฟล์ index.html ที่สืบทอด base.html อยู่
        return render_template('index.html', user=session['user'])
    return redirect(url_for('login_page'))


@app.route('/register', methods=['GET', 'POST'])
def register_page():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not email or not password or not confirm_password:
            return render_template('login.html', message="กรุณากรอกข้อมูลให้ครบถ้วน")
        
        if password != confirm_password:
            return render_template('login.html', message="รหัสผ่านไม่ตรงกัน")
        
        if users_collection.find_one({'email': email}):
            return render_template('login.html', message="อีเมลนี้ถูกใช้งานแล้ว")
        
        hashed_password = generate_password_hash(password)
        users_collection.insert_one({'email': email, 'password': hashed_password})
        
        return redirect(url_for('login_page'))
    
    # เมื่อ method เป็น GET ให้เรียก login.html เพราะทั้ง Login และ Register อยู่ในไฟล์เดียวกัน
    return render_template('login.html')


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            return render_template('login.html', message="กรุณาใส่ Email และ Password")
        
        user = users_collection.find_one({'email': email})
        if user and check_password_hash(user['password'], password):
            session['user'] = email
            return redirect(url_for('index'))
        else:
            return render_template('login.html', message="อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    
    # เมื่อ method เป็น GET ให้แสดงหน้า login
    return render_template('login.html')
    
# Route สำหรับ Forgot Password
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = users_collection.find_one({'email': email})
        
        if user:
            # สร้างโทเค็นที่มีอายุ 30 นาที (1800 วินาที)
            token = s.dumps(email, salt='password-reset-salt')
            send_reset_email(email, token)
            flash('ลิงก์รีเซ็ตรหัสผ่านได้ถูกส่งไปยังอีเมลของคุณแล้ว')
            return redirect(url_for('login_page'))
        else:
            flash('ไม่พบอีเมลนี้ในระบบ')
            return redirect(url_for('forgot_password'))
    
    return render_template('forgot_password.html')

# Route สำหรับ Reset Password
@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        # ตรวจสอบโทเค็น (หมดอายุใน 30 นาที)
        email = s.loads(token, salt='password-reset-salt', max_age=1800)
    except SignatureExpired:
        flash('ลิงก์รีเซ็ตรหัสผ่านหมดอายุแล้ว')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('รหัสผ่านไม่ตรงกัน')
            return redirect(url_for('reset_password', token=token))
        
        hashed_password = generate_password_hash(password)
        users_collection.update_one({'email': email}, {'$set': {'password': hashed_password}})
        flash('รหัสผ่านของคุณถูกรีเซ็ตเรียบร้อยแล้ว')
        return redirect(url_for('login_page'))
    
    return render_template('reset_password.html', token=token)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login_page'))


@app.route('/protected')
def protected():
    if 'user' in session:
        return f"ยินดีต้อนรับ {session['user']} คุณอยู่ในหน้า Protected"
    else:
        return redirect(url_for('login_page'))
    
@app.route('/delete_account', methods=['POST'])
def delete_account():
    if 'user' not in session:
        return jsonify({'error': 'Please log in first'}), 401
    
    email = session['user']
    user = users_collection.find_one({'email': email})
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if users_collection.delete_one({'email': email}):
        session.pop('user', None)
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Failed to delete account'}), 500
    
# Route สำหรับอัปโหลดรูปภาพ
@app.route('/upload_profile_image', methods=['POST'])
def upload_profile_image():
    if 'user' not in session:
        return jsonify({'error': 'Please log in first'}), 401

    email = session['user']
    user = users_collection.find_one({'email': email})

    if not user:
        return jsonify({'error': 'User not found'}), 404

    if 'profile_image' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['profile_image']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename):
        try:
            # 📌 เรียกใช้ resize_image ซึ่งจะลบรูปเก่าถ้ามีมากเกิน 2 รูป
            filename = resize_image(file, email)
            image_url = url_for('static', filename=f'images/{filename}')
            
            # 📌 อัปเดตข้อมูลใน MongoDB ให้ชี้ไปที่รูปใหม่
            users_collection.update_one({'email': email}, {'$set': {'profile_image': image_url}})

            return jsonify({'message': 'Profile image uploaded successfully', 'image_url': image_url})
        except Exception as e:
            return jsonify({'error': f'Error processing image: {str(e)}'}), 500

    return jsonify({'error': 'Invalid file type'}), 400

# อัปเดต Route สำหรับหน้าโปรไฟล์เพื่อส่ง URL รูปภาพ
@app.route('/profile')
def profile():
    if 'user' not in session:
        return redirect(url_for('login_page'))
    
    email = session['user']
    user = users_collection.find_one({'email': email})
    
    if not user:
        flash('ไม่พบข้อมูลผู้ใช้')
        return redirect(url_for('login_page'))
    
    return render_template('profile.html', user=user)

# อัปเดต Route สำหรับอัปเดตโปรไฟล์
@app.route('/update_profile', methods=['POST'])
def update_profile():
    if 'user' not in session:
        return jsonify({'error': 'Please log in first'}), 401
    
    email = session['user']
    user = users_collection.find_one({'email': email})
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # รับข้อมูลจากฟอร์ม (รวมถึงรูปภาพถ้ามี)
    name = request.form.get('name')
    new_email = request.form.get('email')
    
    # ตรวจสอบว่าข้อมูลใหม่ไม่ซ้ำกับผู้ใช้คนอื่น (ยกเว้นตัวเอง)
    if new_email and new_email != email:
        if users_collection.find_one({'email': new_email}):
            return jsonify({'error': 'Email already in use'}), 400
    
    update_data = {}
    if name:
        update_data['name'] = name
    if new_email:
        update_data['email'] = new_email
        session['user'] = new_email  # อัปเดต session ถ้าอีเมลเปลี่ยน
    
    # อัปเดตข้อมูลใน MongoDB
    if update_data or 'profile_image' in request.files:
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file.filename != '':
                if file and allowed_file(file.filename):
                    try:
                        filename = resize_image(file, email)  # ปรับขนาดภาพก่อนบันทึก
                        image_url = url_for('static', filename=f'images/{filename}')
                        update_data['profile_image'] = image_url
                    except Exception as e:
                        return jsonify({'error': f'Error processing image: {str(e)}'}), 500
        
        users_collection.update_one({'email': email}, {'$set': update_data})
        flash('อัปเดตโปรไฟล์สำเร็จ')
    
    return redirect(url_for('profile'))

@app.route('/get_trips', methods=['POST'])
def get_trips():
    province = request.form['province']
    date = request.form['date']
    location = request.form['location']  # รับค่าตำแหน่งที่อยู่ปัจจุบัน

    # ใช้ตำแหน่งที่อยู่ช่วยปรับแต่งทริปให้เหมาะสม
    trips = generate_trips(province, date, location)
    print("Final JSON Response:", jsonify(trips=trips).get_json())  # ✅ ตรวจสอบค่าก่อนส่งกลับ
    return jsonify(trips=trips)


@app.route('/remove_trip', methods=['POST'])
def remove_trip():
    trip_to_remove = request.form['trip']
    province = request.form['province']
    date = request.form['date']
    location = request.form.get('location')

    remaining_trips = json.loads(request.form['trips'])
    trip_index = next((i for i, trip in enumerate(remaining_trips) if trip["title"] == trip_to_remove), None)

    if trip_index is not None:
        # ✅ ตรวจสอบว่าการสร้างทริปใหม่ไม่ส่งคืนลิสต์ว่าง
        new_trips = generate_trips(province, date, location)
        
        if not new_trips:  # ถ้าไม่มีทริปใหม่ให้คืนค่าที่มีอยู่เดิม
            return jsonify(trips=remaining_trips)
            
        new_trip = new_trips[0]  # ใช้ทริปแรกจากลิสต์ใหม่
        remaining_trips[trip_index] = new_trip

    return jsonify(trips=remaining_trips)


# _____________________Weather_____________________

@app.route('/weather')
def weather_page():
    return render_template('weather.html', weather_api_key=WEATHER_API_KEY)




if __name__ == '__main__':
    app.run(debug=True)