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
from PIL import Image, ExifTags
import uuid
import glob
import requests
import random

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

PEXELS_API_KEY = os.getenv('PIXEL_API')  # เปลี่ยนเป็น API Key ของคุณ
PEXELS_BASE_URL = "https://api.pexels.com/v1/search"


places_list = [
    "Bangkok", "Samut Prakan", "Nonthaburi", "Pathum Thani", "Phra Nakhon Si Ayutthaya", "Ang Thong", "Lopburi", "Sing Buri", "Chai Nat", "Saraburi",
    "Nakhon Nayok", "Prachin Buri", "Sa Kaeo", "Chonburi", "Rayong", "Chanthaburi", "Trat", "Chachoengsao",
    "Ratchaburi", "Kanchanaburi", "Suphan Buri", "Nakhon Pathom", "Samut Sakhon", "Samut Songkhram", "Phetchaburi", "Prachuap Khiri Khan",
    "Chumphon", "Ranong", "Surat Thani", "Phang Nga", "Phuket", "Krabi", "Nakhon Si Thammarat", "Trang", "Phatthalung", "Satun", "Songkhla", "Pattani", "Yala", "Narathiwat",
    "Chiang Mai", "Lamphun", "Lampang", "Uttaradit", "Phrae", "Nan", "Phayao", "Chiang Rai", "Mae Hong Son",
    "Nakhon Sawan", "Uthai Thani", "Kamphaeng Phet", "Tak", "Sukhothai", "Phitsanulok", "Phichit", "Phetchabun",
    "Maha Sarakham", "Roi Et", "Kalasin", "Mukdahan", "Yasothon", "Amnat Charoen", "Nong Khai", "Bueng Kan", "Nong Bua Lamphu", "Udon Thani", "Sakon Nakhon", "Nakhon Phanom",
    "Khon Kaen", "Chaiyaphum", "Nakhon Ratchasima", "Buri Ram", "Surin", "Si Sa Ket", "Ubon Ratchathani"
]

def get_trip_image(keyword):
    headers = {"Authorization": PEXELS_API_KEY}
    params = {
        "query": keyword,
        "per_page": 1
    }
    try:
        response = requests.get(PEXELS_BASE_URL, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if "photos" in data and len(data["photos"]) > 0:
            # ดึง URL จาก "medium" size
            return data["photos"][0]["src"]["large"]
        else:
            print(f"No photos found for '{keyword}'")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching image from Pexels for {keyword}: {e}")
    
    # คืนค่า default image หากไม่พบผลลัพธ์
    return url_for('static', filename='images/default_trip.jpg')



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
def generate_trips(province, date_range, num_people, location=None):
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"""สร้างทริปการเดินทาง 3 ทริปที่ไม่ซ้ำกันสำหรับจังหวัด {province} ในวันที่ {date_range} โดยมีจำนวนคน {num_people} คน ให้ระบุเวลาและกิจกรรมแต่ละวันให้ครบถ้วน และต้องไม่มีวันใดหายไป"""
    
    if location:
        prompt += f" และคำนึงถึงตำแหน่งปัจจุบันที่อยู่ใกล้กับ {location}"

    prompt += """
    พร้อมชื่อทริปสั้นๆเป็นภาษาอังกฤษ โดยระบุเวลาที่เป็นไปตามความจริงที่สุด และกิจกรรมอย่างละเอียด รายละเอียดกิจกรรมขอเป็นภาษาไทยทั้งหมด และถ้ามีคำแนะนำก็สามารถใส่เข้ามาได้
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
    print(prompt)
    response = model.generate_content(prompt)
    raw_response = response.text.strip()
    print("Raw Response:", raw_response)  # ✅ ตรวจสอบค่า API Response
    # ✅ ใช้ Regular Expression เพื่อลบ {{ }} ที่อาจเกิดขึ้น
    cleaned_response = re.sub(r'```json|```', '', raw_response)  # ลบ Markdown syntax
    cleaned_response = re.sub(r'{{\s*', '{', cleaned_response)   # ลบ {{
    cleaned_response = re.sub(r'\s*}}', '}', cleaned_response)   # ลบ }}
    cleaned_response = cleaned_response.strip()  # ลบช่องว่างส่วนเกิน
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


def generate_trips_random(province, date_range, num_people, location=None):
    model = genai.GenerativeModel('gemini-2.0-flash')
    prompt = f"สร้างทริปการเดินทาง 3 ทริปที่ไม่ซ้ำกันสำหรับจังหวัด {province} ในช่วงวันที่ {date_range} โดยมีจำนวนคน {num_people} คน"
    
    if location:
        prompt += f" และคำนึงถึงตำแหน่งปัจจุบันที่อยู่ใกล้กับ {location}"

    prompt += """
    พร้อมชื่อทริปสั้นๆเป็นภาษาอังกฤษ โดยระบุเวลาที่เป็นไปตามความจริงที่สุด และกิจกรรมอย่างละเอียด รายละเอียดกิจกรรมขอเป็นภาษาไทยทั้งหมด ถ้าที่เที่ยวในวันนั้นน้อยกว่า2ที่ให้เพิ่มวันได้ ย้ำว่ามีเวลากำกับด้วย และถ้ามีคำแนะนำก็สามารถใส่เข้ามาได้
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
    cleaned_response = re.sub(r'```json|```', '', raw_response)  # ลบ Markdown syntax
    cleaned_response = re.sub(r'{{\s*', '{', cleaned_response)   # ลบ {{
    cleaned_response = re.sub(r'\s*}}', '}', cleaned_response)   # ลบ }}
    cleaned_response = cleaned_response.strip()  # ลบช่องว่างส่วนเกิน
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
            flash('ลิงก์รีเซ็ตรหัสผ่านได้ถูกส่งไปยังอีเมลของคุณแล้ว')
            send_reset_email(email, token)
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
    date_range = request.form['date']  # ช่วงวันที่จากปฏิทิน
    num_people = request.form['num_people']  # จำนวนคน
    location = request.form.get('location', '')  # ตำแหน่งปัจจุบัน (ถ้ามี)

    # ใช้ตำแหน่งที่อยู่ช่วยปรับแต่งทริปให้เหมาะสม
    trips = generate_trips(province, date_range, num_people, location)
    for t in trips:
        t['province'] = province
    print("Final JSON Response:", jsonify(trips=trips).get_json())  # ✅ ตรวจสอบค่าก่อนส่งกลับ
    session['generated_trips'] = trips
    session['province'] = province
    return jsonify(trips=trips)



# _____________________Weather_____________________

@app.route('/weather')
def weather_page():
    return render_template('weather.html', weather_api_key=WEATHER_API_KEY)

@app.route('/location/<trip_title>')
def location(trip_title):
    # ตรวจสอบว่ามาจากหน้า MyTrips หรือไม่
    if request.args.get('saved') == 'true':
        if 'user' not in session:
            flash('กรุณาเข้าสู่ระบบก่อน')
            return redirect(url_for('login_page'))
        
        email = session['user']
        user = users_collection.find_one({'email': email})
        saved_trips = user.get('saved_trips', []) if user else []
        
        # ค้นหาทริปจาก saved_trips
        selected_trip = next((t for t in saved_trips if t['title'] == trip_title), None)
    else:
        # ค้นหาทริปจาก session (ทริปที่เพิ่งสร้าง)
        trips = session.get('generated_trips', [])
        selected_trip = next((t for t in trips if t['title'] == trip_title), None)

    if not selected_trip:
        flash('ไม่พบข้อมูลทริป')
        return redirect(url_for('index'))
    
    # เตรียมข้อมูลจังหวัด
    province = selected_trip.get('province', 'ไม่ทราบจังหวัด')
    
    # โหลดรูปภาพหากจำเป็น
    if 'image' not in selected_trip:
        selected_trip['image'] = get_trip_image(selected_trip['title'])
    
    return render_template('location.html', trip=selected_trip, province=province)

@app.route('/trip')
def trip():
    trips = session.get('generated_trips', [])
    province = session.get('province', 'จังหวัด')
    for trip in trips:
        trip.setdefault('province', province)
        #trip['image'] = get_trip_image(trip['title']) or url_for('static', filename='images/default_trip.jpg')
    return render_template('trip.html', trips = trips, province=province)

@app.route('/save_trip', methods=['POST'])
def save_trip():
    if 'user' not in session:
        return jsonify({'error': 'กรุณาเข้าสู่ระบบก่อน'}), 401
    
    email = session['user']
    trip_data = request.get_json()

    if not trip_data or 'title' not in trip_data or 'province' not in trip_data:
        return jsonify({'error': 'ข้อมูลไม่ถูกต้อง'}), 400

    user = users_collection.find_one({'email': email})
    saved_trips = user.get('saved_trips', [])

    if len(saved_trips) >= 5:
        return jsonify({'error': 'บันทึกทริปได้สูงสุด 5 ทริป กรุณาลบทริปเก่าออกก่อน'}), 400
    
    if any(trip['title'] == trip_data['title'] for trip in saved_trips):
        return jsonify({'error': 'ทริปนี้ถูกบันทึกไว้แล้ว'}), 400
    
    users_collection.update_one(
        {'email': email},
        {'$push': {'saved_trips': trip_data}},
        upsert=True
    )

    return jsonify({'success': True})

@app.route('/mytrips')
def mytrips():
    if 'user' not in session:
        return redirect(url_for('login_page'))
    
    email = session['user']
    user = users_collection.find_one({'email': email})
    saved_trips = user.get('saved_trips', []) if user else []

    return render_template('mytrip.html', trips=saved_trips)

@app.route('/delete_trip', methods=['POST'])
def delete_trip():
    if 'user' not in session:
        return jsonify({'error': 'กรุณาเข้าสู่ระบบก่อน'}), 401
    
    email = session['user']
    trip_title = request.json.get('title')

    users_collection.update_one(
        {'email': email},
        {'$pull': {'saved_trips': {'title': trip_title}}}
    )

    return jsonify({'success': True})

@app.route('/get_trip_image')
def get_trip_image_endpoint():
    title = request.args.get('title', '')
    image_url = get_trip_image(title)
    return image_url

@app.route('/random_place')
def random_place():
    random_province = random.choice(places_list)  # สุ่มจังหวัด
    trips = generate_trips_random(random_province, None, num_people=1)  # สร้างทริป

    if trips and len(trips) > 0:
        trip = trips[0]  # เอาทริปแรกมาใช้
        trip_title = trip.get("title", "ทริปไม่มีชื่อ")  # ถ้าไม่มีชื่อ ให้ใช้ข้อความเริ่มต้น
        trip_image = get_trip_image(trip_title)  # ดึงรูปภาพ
        trip["image"] = trip_image
        trip["province"] = random_province  # เก็บจังหวัดไว้
        session['random_trip'] = trip  # เก็บลง session

        return jsonify({
            "title": trip_title,   # ส่งชื่อทริปไป
            "province": random_province,  # จังหวัด
            "image": trip_image   # รูปภาพ
        })
    
    return jsonify({"error": "No trips available"}), 500

@app.route('/location/random_trip')
def location_random_trip():
    trip = session.get('random_trip')

    if not trip:
        flash('ไม่มีข้อมูลทริป กรุณาลองใหม่')
        return redirect(url_for('index'))

    return render_template('location.html', trip=trip, province=trip.get('province', ''))



if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)