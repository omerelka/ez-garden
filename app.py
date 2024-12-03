import firebase_admin
import requests
import asyncio
import json
from datetime import datetime, timedelta
from firebase_admin import credentials, firestore
from flask import Flask, render_template, request, redirect, session
from flask_caching import Cache
from openplantbook_sdk import OpenPlantBookApi, MissingClientIdOrSecret, ValidationError



SENSOR_API_LOGIN_URL = "https://atapi.atomation.net/auth/login"
SENSOR_API_READINGS_URL = "https://atapi.atomation.net/sensors_readings"
OPENPLANT_API_BASE_URL = "https://open.plantbook.io/api/v1"
SENSOR_APP_VERSION = "1.0.0"
SENSOR_ACCESS_TYPE = 5


BASE_URL = "https://open.plantbook.io/api/v1"
CLIENT_ID = "tC0yqwKuCLpFRkFNjTFsHugNJo6poO0I8neJFZuR"
CLIENT_SECRET = "Fny45ACTmtXTOwpC5j3b00HeDgvboHZMh8mjbH190FmeNBNsAWH3mjNm6gYNg38FMyszvzTzhsy2GRdhPb8YcY6uMmD4NYnhhUKPac8a6h1Zgh35IIjDrfRDqYiGmTdT"


app = Flask(__name__)


app.config['CACHE_TYPE'] = 'SimpleCache'
app.config['CACHE_DEFAULT_TIMEOUT'] = 3600  # זמן מטמון (בשניות) - שעה
cache = Cache(app)

app.secret_key = "ezgarden"



cred = credentials.Certificate("ez-garden-firebase-adminsdk-rr8ir-08d2cdc1d0.json")
firebase_admin.initialize_app(cred)
db = firestore.client()



@app.context_processor
def inject_user_info():
    """Inject user info into all templates."""
    user_email = session.get("user_email")
    
    return {"user_email": user_email}




@app.route('/')
def home():
    return render_template('home1.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            return render_template('login.html', error_message="Both email and password are required!")

        # בדיקה אם המשתמש הוא עובד
        employees_ref = db.collection("employees").where("company_email", "==", email).where("password", "==", password).get()

        if employees_ref:
            employee_data = employees_ref[0].to_dict()
            role = employee_data.get("role", 1)  # דרגת ההרשאה
            company_name = employee_data.get("company_name")

            # שמירת פרטי העובד ב-Session
            session['user_email'] = email
            session['user_role'] = role
            session['company_name'] = company_name

            if role == 1:  # עובד בסיסי
                return redirect("/home_company_1")
            elif role == 2:  # עובד מורשה
                return redirect("/home_company_2")
            elif role == 3:  # מנהל
                return redirect("/home_company_3")

        # בדיקה אם המשתמש הוא פרטי
        users_ref = db.collection("users").where("email", "==", email).where("password", "==", password).get()
        if users_ref:
            session['user_email'] = email
            session['user_type'] = "private"
            return redirect("/home3")

        return render_template('login.html', error_message="Invalid email or password!")

    return render_template('login.html')


@app.route('/register_type')
def register_type():
    return render_template('register_type.html')


@app.route('/register_private', methods=['GET', 'POST'])
def register_private():
    if request.method == 'POST':
        fullname = request.form.get('fullname')
        email = request.form.get('email')
        password = request.form.get('password')

        if not fullname or not email or not password:
            return render_template('register_private.html', error_message="All fields are required!")

        # שמירת נתוני משתמש פרטי בפיירבייס
        user_data = {
            "type": "private",
            "fullname": fullname,
            "email": email,
            "password": password
        }
        db.collection("users").add(user_data)

        # הצגת הודעה לאחר הרשמה
        return render_template('success.html', message=f"User {fullname} successfully registered with email {email}!")

    return render_template('register_private.html')


@app.route('/register_company', methods=['GET', 'POST'])
def register_company():
    if request.method == 'POST':
        company_name = request.form.get('company_name')
        name = request.form.get('name')
        company_email = request.form.get('email')
        password = request.form.get('password')

        # בדיקה אם כל השדות מלאים
        if not company_name or not name or not company_email or not password:
            return render_template('register_company.html', error_message="All fields are required!")

        # שמירת נתוני החברה בפיירבייס
        company_data = {
            "company_name": company_name,
            "name": name,
            "company_email": company_email,
            "password": password,
            "role": 3  # דרגת מנהל
        }
        db.collection("employees").add(company_data)

        # הודעה למשתמש על ההצלחה
        success_message = f"The company {company_name} has been successfully registered with the email {company_email}!"
        return render_template('success.html', message=success_message)

    return render_template('register_company.html')



@app.route('/home_company_3')
def home_company_3():
    return render_template('home_company_3.html')


@app.route('/home_company_2')
def home_company_2():
    return render_template('home_company_2.html')



@app.route('/home_company_1')
def home_company_1():
    return render_template('home_company_1.html')






@app.route("/employee_management", methods=["GET", "POST"])
def employee_management():
    company_email = session.get("user_email")
    company_name = session.get("company_name")
    
    # אימייל המנהל המחובר
    if not company_email:
        print("No company email in session. Redirecting to login.")
        return redirect('/login')  # אם אין אימייל במערכת, חזור למסך כניסה

    if request.method == 'POST':
        # קבלת נתונים מהטופס
        employee_name = request.form.get('employee_name')
        employee_password = request.form.get('employee_password')
        employee_role = request.form.get('employee_role')

        # בדיקת נתוני הטופס
        if not employee_name or not employee_password or not employee_role:
            print("Missing field(s) in the form submission.")
            return render_template(
                'employee_management.html',
                error_message="All fields are required!",
                employees=get_employees_from_db(company_email)
            )

        if not employee_role.isdigit() or int(employee_role) not in [1, 2, 3]:
            print("Invalid role value.")
            return render_template(
                'employee_management.html',
                error_message="Role must be 1, 2, or 3!",
                employees=get_employees_from_db(company_email)
            )

        # הכנת הנתונים ל-Firebase
        employee_data = {
            "company_name": company_name.strip(),
            "company_email": company_email.strip(),
            "name": employee_name.strip(),
            "password": employee_password.strip(),
            "role": int(employee_role)
            
        }

        # שמירה ב-Firebase
        try:
            print("Attempting to add employee to Firebase:", employee_data)
            db.collection("employees").add(employee_data)
            print("Successfully added employee:", employee_data)
        except Exception as e:
            print("Error adding employee to Firebase:", e)
            return render_template(
                'employee_management.html',
                error_message="Failed to save employee to the database!",
                employees=get_employees_from_db(company_email)
            )

        return redirect('/employee_management')

    # GET request - משיכת נתונים של כל העובדים באותה חברה
    try:
        employees = get_employees_from_db(company_email)
        print("Employees retrieved from database:", employees)
    except Exception as e:
        print("Error retrieving employees:", e)
        return render_template(
            'employee_management.html',
            error_message="Failed to retrieve employees!",
            employees=[]
        )

    return render_template('employee_management.html', employees=employees)


def get_employees_from_db(company_email):
    """ פונקציה לשליפת עובדים מאותה חברה """
    try:
        employees_ref = db.collection("employees").where("company_email", "==", company_email).stream()
        employees = []
        for emp in employees_ref:
            employee_data = emp.to_dict()
            employee_data['id'] = emp.id  # שמירת ה-ID של המסמך
            employees.append(employee_data)
        return employees
    except Exception as e:
        print("Error retrieving employees from Firebase:", e)
        return []

@app.route("/delete_employee/<employee_id>", methods=["POST"])
def delete_employee(employee_id):
    try:
        # מחיקת העובד על פי ה-ID
        db.collection("employees").document(employee_id).delete()
        print(f"Employee {employee_id} deleted successfully.")
    except Exception as e:
        print(f"Error deleting employee {employee_id}: {e}")
        return redirect('/employee_management')

    # חזרה לעמוד ניהול עובדים
    return redirect('/employee_management')













@app.route('/home3')
def home3():
    user_email = session.get('user_email')  # קבלת האימייל מה-Session

    if not user_email:
        return redirect('/login')  # אם המשתמש לא מחובר, הפניה לעמוד ההתחברות

    # חיפוש הצמחים של המשתמש ב-Firebase
    plants_ref = db.collection("plants")
    query = plants_ref.where("user_email", "==", user_email).get()

    # יצירת רשימת צמחים עם Document ID
    plants = [
    {
        "id": plant.id,  # Document ID
        "area": plant.to_dict().get("area", "Unknown"),  # ערך ברירת מחדל
        "type": plant.to_dict().get("type", "Unknown")   # ערך ברירת מחדל
    }
    for plant in query
    ]

    # שליחה ל-home3.html
    return render_template('home3.html', plants=plants)



@app.route('/delete_plant/<plant_id>', methods=['POST'])
def delete_plant(plant_id):
    user_email = session.get('user_email')

    if not user_email:
        return redirect('/login')

    db.collection("plants").document(plant_id).delete()

    return redirect('/home3')




@app.route('/add_plant', methods=['GET', 'POST'])
def add_plant():
    user_email = session.get('user_email')  # קבלת האימייל מה-Session

    if not user_email:
        return redirect('/login')  # אם המשתמש לא מחובר, הפניה לעמוד ההתחברות

    if request.method == 'POST':
        area = request.form.get('area')
        type = request.form.get('type')

        if not area or not type:
            return "<h1 style='text-align:center; color:red;'>All fields are required!</h1>"

        # שמירת הצמח ב-Firebase
        plant_data = {
            "area": area,
            "type": type,
            "user_email": user_email
        }
        db.collection("plants").add(plant_data)

        return redirect("/home3")

    return render_template('add_plant.html')




# פונקציה לקבלת ה-Access Token
def get_access_token(client_id, client_secret):
    url = "https://open.plantbook.io/api/v1/token/"
    data = {
        "grant_type": "client_credentials",
        "client_id": 'tC0yqwKuCLpFRkFNjTFsHugNJo6poO0I8neJFZuR',
        "client_secret": 'Fny45ACTmtXTOwpC5j3b00HeDgvboHZMh8mjbH190FmeNBNsAWH3mjNm6gYNg38FMyszvzTzhsy2GRdhPb8YcY6uMmD4NYnhhUKPac8a6h1Zgh35IIjDrfRDqYiGmTdT',
        "scope": "read"
    }

    response = requests.post(url, data=data)

    if response.status_code == 200:
        token_data = response.json()
        return token_data.get("access_token")
    else:
        print(f"Error: Unable to fetch token. Status code: {response.status_code}")
        print(f"Response: {response.text}")
        return None


# פונקציה אסינכרונית לקבלת פרטי הצמח
async def get_plant_details(plant_type, access_token):
    url = f"https://open.plantbook.io/api/v1/plant/search?alias={plant_type}"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            search_results = response.json()
            if search_results and 'results' in search_results and len(search_results['results']) > 0:
                plant = search_results['results'][0]  # התוצאה הראשונה
                plant_pid = plant['pid']
                
                # קבלת פרטי הצמח על פי PID
                detail_url = f"https://open.plantbook.io/api/v1/plant/detail/{plant_pid}"
                detail_response = requests.get(detail_url, headers=headers)
                
                if detail_response.status_code == 200:
                    return detail_response.json()
                else:
                    print(f"Error fetching plant details: {detail_response.status_code}")
                    return None
            else:
                print("No results found for the plant type.")
                return None
        else:
            print(f"Error fetching plant data: {response.status_code}")
            return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None



def get_sensor_api_token():

    url = "https://atapi.atomation.net/api/v1/s2s/v1_0/auth/login"
    headers = {
        "accept": "application/json",
        "app_version": "v1.0",
        "access_type": "5",
        "Content-Type": "application/json"
    }
    payload = {
        "email": "sce@atomation.net",
        "password": "123456"
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        
        data = response.json()
        token = data.get("data", {}).get("token")
        if token:
            print("Token successfully retrieved!")
            return token
        else:
            print("Error: Token not found in response.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching token: {e}")
        return None



def get_last_sensor_reading(token, mac_address):
    # כתובת URL מעודכנת
    url = "https://atapi.atomation.net/api/v1/s2s/v1_0/sensors_readings"

    if not mac_address:
        print("שגיאה: כתובת MAC לא סופקה.")
        return {"error": "MAC address is missing."}

    # יצירת טווח תאריכים בפורמט ISO
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(hours=1)
    formatted_start_date = start_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    formatted_end_date = end_date.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    print("Start Date:", formatted_start_date)
    print("End Date:", formatted_end_date)

    # גוף הבקשה
    payload = {
        "filters": {
            "start_date": formatted_start_date,
            "end_date": formatted_end_date,
            "mac": [mac_address],
            "createdAt": True
        },
        "limit": {
            "page": 1,
            "page_size": 1
        }
    }

    # כותרות הבקשה עם האסימון
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        # שליחת בקשת POST ל-API
        response = requests.post(url, data=json.dumps(payload), headers=headers)
        print(f"Response Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print("Response Data:", data)

            # בדיקה האם יש נתונים במפתח readings_data
            if "data" in data and "readings_data" in data["data"]:
                readings_data = data["data"]["readings_data"]
                if isinstance(readings_data, list) and len(readings_data) > 0:
                    return readings_data[0]  # הקריאה האחרונה
                else:
                    print("לא נמצאו נתונים לחיישן זה או שהנתונים ריקים.")
                    return {"message": "No sensor data available."}
            else:
                print("מבנה הנתונים שונה או חסרים נתונים.")
                return {"error": "Unexpected data structure from API response."}
        else:
            print(f"שגיאה בקבלת קריאת חיישן: {response.status_code}")
            print("תוכן התגובה:", response.text)
            return {"error": f"Sensor API returned status code {response.status_code}"}
    except json.JSONDecodeError:
        print("שגיאה: התגובה אינה בפורמט JSON.")
        return {"error": "Response is not a valid JSON."}
    except Exception as e:
        print(f"שגיאה כללית: {e}")
        return {"error": f"An unexpected error occurred: {e}"}


# Flask Route להצגת פרטי צמח
@app.route('/plant_details/<plant_type>')
def plant_details(plant_type):

    # קבלת ה-Access Token
    access_token = get_access_token(CLIENT_ID, CLIENT_SECRET)
    if not access_token:
        return "Error: Unable to retrieve access token.", 500

    # קבלת פרטי הצמח בצורה סינכרונית
    details = asyncio.run(get_plant_details(plant_type, access_token))
    
    # בדיקת תוצאה
    if not details:
        return "Error: Unable to retrieve plant details.", 500
    
    
    
    
    
    
    
    
    sensor_token = cache.get("sensor_api_token")
    if not sensor_token:
        # אם ה-token לא במטמון, נבצע login
        sensor_token = get_sensor_api_token()
        if not sensor_token:
            return "Error: Unable to retrieve sensor token.", 500

        # שמירת ה-token במטמון עם זמן תפוגה (לדוגמה, שעה)
        cache.set("sensor_api_token", sensor_token, timeout=3600)

    # בדיקת מטמון עבור הנתונים של החיישן
    sensor_cache_key = "last_sensor_reading"
    sensor_data = cache.get(sensor_cache_key)
    if not sensor_data:
        # קבלת קריאה אחרונה מהחיישן
        sensor_data = get_last_sensor_reading(sensor_token, "E9:19:79:09:A1:AD")
        if sensor_data:
            cache.set(sensor_cache_key, sensor_data, timeout=300)  # שמירת קריאה אחרונה במטמון ל-5 דקות

    return render_template('plant_details.html', plant=details, sensor=sensor_data)





if __name__ == "__main__":
    app.run(debug=True)