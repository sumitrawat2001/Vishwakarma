import atexit
import base64
import io
import json
import math
import os
import random
import re
import smtplib
import uuid
import zipfile
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bson import ObjectId
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_pymongo import PyMongo
from pymongo.errors import PyMongoError
from werkzeug.security import check_password_hash, generate_password_hash
from construction_modules import (
    FileResourceRepository,
    MongoResourceRepository,
    RESOURCE_SCHEMAS,
    ResourceValidationError,
    serialize_resource,
    validate_resource,
)

import logging

load_dotenv()
logger = logging.getLogger('vishwakarma_ai')
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'development-only-change-me')
app.config['MONGO_URI'] = os.getenv('MONGO_URI', 'mongodb://localhost:27017/smart_house_planner?serverSelectionTimeoutMS=2000')
mongo = PyMongo()
mongo.init_app(app, uri=app.config['MONGO_URI'])
atexit.register(mongo.cx.close)


@app.route('/manifest.webmanifest')
def pwa_manifest():
    return app.response_class(
        response=json.dumps({
            'name': 'Smart House Planner',
            'short_name': 'Smart House',
            'start_url': '/dashboard',
            'display': 'standalone',
            'background_color': '#f7f5ef',
            'theme_color': '#ed6b42',
            'description': 'Preliminary house planning, estimates, and 3D visualization.'
        }),
        mimetype='application/manifest+json'
    )

@app.route('/service-worker.js')
def pwa_service_worker():
    return app.response_class(
        response="""const CACHE = 'smart-house-v1';
const APP_SHELL = ['/login', '/register', '/static/css/style.css', '/static/css/polish.css', '/static/js/app.js'];
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(APP_SHELL))));
self.addEventListener('fetch', event => event.respondWith(fetch(event.request).catch(() => caches.match(event.request))));
""",
        mimetype='application/javascript'
    )

ROOMS = ['Bedroom', 'Master Bedroom', 'Living Room', 'Kitchen', 'Bathroom', 'Dining Room', 'Balcony', 'Store Room', 'Study Room', 'Parking']
ROOM_DIMENSIONS = {
    'Bedroom': {'width': 12, 'depth': 10},
    'Master Bedroom': {'width': 14, 'depth': 12},
    'Living Room': {'width': 16, 'depth': 12},
    'Kitchen': {'width': 10, 'depth': 9},
    'Bathroom': {'width': 8, 'depth': 7},
    'Dining Room': {'width': 12, 'depth': 10},
    'Balcony': {'width': 8, 'depth': 6},
    'Store Room': {'width': 8, 'depth': 8},
    'Study Room': {'width': 10, 'depth': 8},
    'Parking': {'width': 16, 'depth': 10},
}
MATERIAL_FACTORS = {'cement': 0.45, 'sand': 0.045, 'aggregate': 0.09, 'bricks': 8, 'steel': 4, 'flooring': 0.9, 'paint': 3.5}

USER_STORE_PATH = Path(__file__).resolve().parent / '.users.json'
PROJECT_STORE_PATH = Path(__file__).resolve().parent / '.projects.json'
RESOURCE_STORE_PATH = Path(__file__).resolve().parent / '.construction_resources.json'
SUPPORT_KNOWLEDGE_PATH = Path(__file__).resolve().parent / '.support_knowledge.json'
SUPPORT_CHAT_PATH = Path(__file__).resolve().parent / '.support_chat.json'
SUPPORT_TICKETS_PATH = Path(__file__).resolve().parent / '.support_tickets.json'

DEFAULT_SUPPORT_KNOWLEDGE = {
    'faqs': [
        {
            'keywords': ['3d', 'three', 'view', 'render', 'canvas'],
            'answer': 'Open the planner, then use the 3D View button. If the canvas stays blank, refresh the page and ensure the browser allows script execution. The app now includes a safe 3D renderer plus fallback styling.',
            'category': 'planner'
        },
        {
            'keywords': ['login', 'sign in', 'password', 'access'],
            'answer': 'Use the Log in page with your registered email and password. If you forgot your password, create a new account and then use the same email to access your saved plans.',
            'category': 'account'
        },
        {
            'keywords': ['save', 'project', 'saved', 'planner'],
            'answer': 'After designing the layout, enter a project name and click Save Project in the planner. Your plan is stored in the project store and can be opened from the Projects dashboard.',
            'category': 'projects'
        },
        {
            'keywords': ['report', 'pdf', 'download'],
            'answer': 'Open a saved project and use the Report option to generate a PDF summary. The report includes plot details, built-up area, and a preliminary estimate for review.',
            'category': 'reports'
        },
        {
            'keywords': ['mobile', 'phone', 'network', 'wifi', 'install'],
            'answer': 'The app is configured for mobile and local network access. Run it on 0.0.0.0, confirm the IP/port, and use the browser on the same network. A manifest and service worker are included for installable behavior.',
            'category': 'deployment'
        },
        {
            'keywords': ['mongo', 'database', 'mongodb', 'error'],
            'answer': 'If MongoDB is unavailable, the app automatically falls back to local JSON stores for auth and project data. You can still use the app while MongoDB is being set up.',
            'category': 'database'
        }
    ]
}

SUPPORT_LANGUAGE_ALIASES = {
    'planner': ['3d view nahi chal raha', '3d view nahi aa raha', '3d नहीं चल रहा', 'थ्रीडी', 'मॉडल नहीं दिख रहा', 'render nahi ho raha'],
    'account': ['login nahi ho raha', 'लॉगिन नहीं हो रहा', 'पासवर्ड भूल गया', 'sign in nahi ho raha', 'account problem'],
    'projects': ['project save nahi ho raha', 'प्रोजेक्ट सेव नहीं हो रहा', 'plan save nahi ho raha', 'योजना सेव'],
    'reports': ['report download nahi ho rahi', 'रिपोर्ट डाउनलोड नहीं हो रही', 'pdf nahi mil rahi', 'रिपोर्ट चाहिए'],
    'deployment': ['phone par nahi chal raha', 'मोबाइल पर नहीं चल रहा', 'wifi se connect nahi ho raha', 'फोन में नहीं खुल रहा'],
    'database': ['database error', 'डेटाबेस एरर', 'mongodb down', 'डेटाबेस काम नहीं कर रहा'],
}

SUPPORT_LOCALIZED_ANSWERS = {
    'planner': {
        'hi': 'Planner खोलें और 3D View बटन दबाएं। अगर canvas खाली दिखे, तो page refresh करें और browser में JavaScript की अनुमति जांचें।',
        'hinglish': 'Planner kholo aur 3D View button dabao. Agar canvas blank dikhe, page refresh karo aur browser mein JavaScript allow hai ya nahi check karo.',
    },
    'account': {
        'hi': 'Log in page पर registered email और password से प्रवेश करें। Password भूल गए हों तो नया account बनाकर saved plans खोलें।',
        'hinglish': 'Log in page par registered email aur password use karo. Password bhool gaye ho to naya account bana kar saved plans kholo.',
    },
    'projects': {
        'hi': 'Planner में layout बनाने के बाद project name भरें और Save Project दबाएं। आपका plan Projects dashboard में मिल जाएगा।',
        'hinglish': 'Planner mein layout banane ke baad project name bharo aur Save Project dabao. Plan Projects dashboard mein mil jayega.',
    },
    'reports': {
        'hi': 'Saved project खोलें और Report option चुनें। वहां से preliminary PDF summary download की जा सकती है।',
        'hinglish': 'Saved project kholo aur Report option select karo. Wahan se preliminary PDF summary download kar sakte ho.',
    },
    'deployment': {
        'hi': 'App को 0.0.0.0 पर चलाएं, सही IP और port जांचें, फिर उसी Wi-Fi पर mobile browser से खोलें।',
        'hinglish': 'App ko 0.0.0.0 par chalao, IP aur port check karo, phir same Wi-Fi par mobile browser se kholo.',
    },
    'database': {
        'hi': 'MongoDB उपलब्ध न होने पर app local JSON storage पर चली जाती है। MongoDB शुरू करके फिर कोशिश करें।',
        'hinglish': 'MongoDB available na ho to app local JSON storage par chalti hai. MongoDB start karke dobara try karo.',
    },
}

SUPPORT_FALLBACK_ANSWERS = {
    'hi': 'मैं login, dashboard, project save, report, 3D planner, mobile/network और deployment में मदद कर सकता हूं। अगर आप किसी सूचीबद्ध module से अलग feature पूछ रहे हैं, तो वह Vishwakarma में अभी उपलब्ध नहीं हो सकता। कृपया अपनी समस्या थोड़ी और बताएं।',
    'hinglish': 'Main login, dashboard, project save, report, 3D planner, mobile/network aur deployment mein help kar sakta hoon. Agar aap kisi listed module se alag feature pooch rahe ho, to woh Vishwakarma mein abhi available nahi ho sakta. Apni problem thodi detail mein batao.',
}

VISHWAKARMA_PROJECT_KNOWLEDGE = {
    'name': 'VISHWAKARMA - Smart Building Constructor & Estimator',
    'purpose': 'A Flask application for preliminary house planning, material and cost estimation, renewable-water planning, saved projects, reports, sharing, and educational simulations.',
    'modules': {
        'overview': 'Home and About explain the product and its preliminary-estimate scope.',
        'account': 'Register, login, password reset, and optional email/mobile verification are available. File JSON stores are used when MongoDB is unavailable.',
        'dashboard': 'Shows recent saved projects, built-up area, indicative cost, solar output, and rainwater potential.',
        'planner': 'Planner accepts plot length, plot width, unit, floors, room counts, and room dimensions. It computes plot area, 70% preliminary coverage, built-up area, and open area, and can save a project.',
        'visualization': 'Planner includes a 2D layout workflow and a 3D View control with front, side, top, floor selection, and building style controls.',
        'materials': 'Material estimator uses calculate_materials(area, floors). Factors per sq ft per floor are cement 0.45, sand 0.045, aggregate 0.09, bricks 8, steel 4, flooring 0.9, and paint 3.5.',
        'cost': 'The /cost page sums user-entered category costs and adds a 5% contingency. What-if construction cost uses built-up area * 140 + floors * 2500.',
        'solar': 'Solar estimate uses monthly usage / (30 * sunlight hours * 0.8), then rounds up panel count from capacity and panel wattage.',
        'rainwater': 'Rainwater estimate uses roof area * annual rainfall * runoff coefficient for litres per year, then divides by 12 for monthly potential.',
        'simulation': 'Simulation Lab includes material, load, rainwater, solar, construction cost, what-if, 3D visualization, save, and PDF export. Results are educational and indicative.',
        'projects': 'Saved projects can be opened, edited in the planner, deleted, reported as PDF, shared, commented on, assigned team members, and viewed through version history.',
        'support': 'Support uses the built-in knowledge base, trained Q&A, calculator context, saved project context, and optional OpenAI-compatible AI.',
        'deployment': 'Run with python app.py. The app binds to 0.0.0.0 and defaults to port 5000. Configure SECRET_KEY and optional MONGO_URI and AI variables in .env.',
    },
    'limitations': 'All construction, material, solar, rainwater, load, and cost outputs are preliminary educational estimates. They are not certified structural, electrical, architectural, quantity-surveying, or approval documents.',
}

AI_INTENT_ALIASES = {
    'overview': ['what is vishwakarma', 'vishwakarma kya hai', 'about this app', 'what does this app do', 'features'],
    'planner': ['house plan', 'ghar ka plan', 'घर का प्लान', 'create plan', 'make a plan', 'plot', 'room size', 'कमरे का आकार', 'floor', 'मंजिल'],
    'materials': ['material', 'cement', 'सीमेंट', 'sand', 'रेत', 'aggregate', 'गिट्टी', 'brick', 'ईंट', 'steel', 'सरिया'],
    'cost': ['cost', 'लागत', 'कीमत', 'budget', 'estimate', 'construction price', 'बनाने का खर्च'],
    'solar': ['solar', 'सोलर', 'panel', 'पैनल', 'electricity usage'],
    'rainwater': ['rainwater', 'rain water', 'बारिश का पानी', 'water harvesting', 'जल संचयन'],
    'simulation': ['simulation', 'सिमुलेशन', 'what-if', 'what if', 'scenario'],
    'projects': ['saved project', 'project save', 'project edit', 'project sharing', 'team member', 'save project', 'प्रोजेक्ट सेव'],
    'reports': ['report', 'pdf', 'रिपोर्ट', 'पीडीएफ'],
    'account': ['login', 'log in', 'register', 'signup', 'password', 'लॉगिन', 'पासवर्ड'],
}

AI_LOCAL_ANSWERS = {
    'overview': 'Vishwakarma is this project-specific Smart Building Constructor & Estimator. It combines a house planner, material and cost estimators, solar and rainwater calculators, saved projects, reports, sharing, and an educational Simulation Lab.',
    'planner': 'Open Planner, enter plot length and width, choose the unit and number of floors, select rooms, adjust room dimensions, and use Save Project when the layout is ready. The planner uses a preliminary 70% plot-coverage assumption for built-up area.',
    'materials': 'Open Materials and enter built-up area and floors. The app estimates cement, sand, aggregate, bricks, steel, flooring, and paint using its existing per-area factors. Treat the result as an approximate planning estimate.',
    'cost': 'The /cost page accepts your Civil work, Materials, Labour, Electrical, Plumbing, Flooring, Painting, Doors and windows, and Other expenses values, then adds a 5% contingency. The What-if simulator separately uses built-up area × 140 + floors × 2,500.',
    'solar': 'Solar uses monthly electricity usage, panel wattage, and sunlight hours. The current formula estimates capacity as monthly usage ÷ (30 × sunlight hours × 0.8), then rounds up the panel count.',
    'rainwater': 'Rainwater uses roof area × annual rainfall × runoff coefficient for litres per year and divides by 12 for monthly potential. Use local rainfall and roof data for a better estimate.',
    'simulation': 'Simulation Lab contains Material, Load, Solar, Rainwater, Cost, What-if, and 3D visualization modules. It is for educational and preliminary planning only, not professional certification.',
    'projects': 'Use Save Project in Planner to create a saved project. Saved projects can be opened and edited, reported as PDF, shared, commented on, assigned team members, and reviewed through version history.',
    'reports': 'Open a saved project and choose Report. The report page provides the project summary and the PDF report route for download.',
    'account': 'Use Register to create an account and Log in to access the dashboard and saved project features. Password reset and optional verification are also available.',
}


def _has_openai_config():
    return bool(os.getenv('OPENAI_API_KEY'))


def _has_azure_config():
    return bool(os.getenv('AZURE_OPENAI_API_KEY') and os.getenv('AZURE_OPENAI_ENDPOINT') and os.getenv('AZURE_OPENAI_DEPLOYMENT'))


def _env_bool(name, default=False):
    return str(os.getenv(name, default)).strip().lower() in {'1', 'true', 'yes', 'on'}


def verification_providers_configured():
    configured_values = [
        os.getenv('SMTP_HOST', ''),
        os.getenv('SMTP_USERNAME', ''),
        os.getenv('MAIL_USERNAME', ''),
        os.getenv('TWILIO_ACCOUNT_SID', ''),
        os.getenv('SENDGRID_API_KEY', ''),
        os.getenv('FIREBASE_PROJECT_ID', ''),
    ]
    placeholder_values = {'', 'changeme', 'change-me', 'example', 'replace_me', 'replace-me', 'your_smtp_username', 'your_twilio_account_sid'}
    return any((value or '').strip().lower() not in placeholder_values for value in configured_values)


def send_email_message(to_email, subject, body):
    smtp_host = os.getenv('SMTP_HOST')
    smtp_sender = os.getenv('SMTP_SENDER_EMAIL') or os.getenv('SMTP_USERNAME') or os.getenv('MAIL_USERNAME')
    if smtp_host and smtp_sender:
        try:
            message = EmailMessage()
            message['Subject'] = subject
            message['From'] = smtp_sender
            message['To'] = to_email
            message.set_content(body)
            with smtplib.SMTP(smtp_host, int(os.getenv('SMTP_PORT', '587') or 587)) as server:
                if _env_bool('SMTP_USE_TLS', True):
                    server.starttls()
                username = os.getenv('SMTP_USERNAME') or os.getenv('MAIL_USERNAME')
                password = os.getenv('SMTP_PASSWORD') or os.getenv('MAIL_PASSWORD')
                if username and password:
                    server.login(username, password)
                server.send_message(message)
            return True
        except Exception as exc:
            print(f'[auth-email] SMTP send failed: {exc}')

    sendgrid_key = os.getenv('SENDGRID_API_KEY')
    if sendgrid_key and smtp_sender:
        try:
            payload = {
                'personalizations': [{'to': [{'email': to_email}]}],
                'from': {'email': smtp_sender},
                'subject': subject,
                'content': [{'type': 'text/plain', 'value': body}],
            }
            request = Request(
                'https://api.sendgrid.com/v3/mail/send',
                data=json.dumps(payload).encode('utf-8'),
                headers={
                    'Authorization': f'Bearer {sendgrid_key}',
                    'Content-Type': 'application/json',
                },
                method='POST',
            )
            with urlopen(request, timeout=30):
                return True
        except Exception as exc:
            print(f'[auth-email] SendGrid send failed: {exc}')

    print(f'[auth-email] No configured mail provider. Email to {to_email} not delivered. Subject: {subject}')
    return False


def send_whatsapp_message(phone_number, body):
    twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
    twilio_token = os.getenv('TWILIO_AUTH_TOKEN')
    twilio_from = os.getenv('TWILIO_WHATSAPP_NUMBER') or os.getenv('TWILIO_FROM_NUMBER')
    if not (twilio_sid and twilio_token and twilio_from and phone_number):
        return False

    if not str(phone_number).startswith('whatsapp:'):
        phone_number = phone_number.strip()
        if not phone_number.startswith('+'):
            phone_number = f'+{phone_number}'
        destination = f'whatsapp:{phone_number}'
    else:
        destination = phone_number

    try:
        content_sid = os.getenv('TWILIO_WHATSAPP_CONTENT_SID')
        if content_sid:
            content_variables = os.getenv('TWILIO_WHATSAPP_CONTENT_VARIABLES', '{"1": "{{otp}}"}')
            content_variables = content_variables.replace('{{otp}}', body.rsplit(' is ', 1)[-1].split('.')[0])
            message_fields = {
                'To': destination,
                'From': twilio_from,
                'ContentSid': content_sid,
                'ContentVariables': content_variables,
            }
        else:
            message_fields = {'To': destination, 'From': twilio_from, 'Body': body}
        data = urlencode(message_fields).encode('utf-8')
        auth = base64.b64encode(f'{twilio_sid}:{twilio_token}'.encode()).decode('utf-8')
        request = Request(
            f'https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json',
            data=data,
            headers={
                'Authorization': f'Basic {auth}',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            method='POST',
        )
        with urlopen(request, timeout=30):
            return True
    except Exception as exc:
        print(f'[auth-whatsapp] Twilio WhatsApp send failed: {exc}')
        return False


def send_sms_message(phone_number, body, channel='sms'):
    if channel == 'whatsapp':
        return send_whatsapp_message(phone_number, body)

    twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
    twilio_token = os.getenv('TWILIO_AUTH_TOKEN')
    twilio_from = os.getenv('TWILIO_FROM_NUMBER')
    if twilio_sid and twilio_token and twilio_from and phone_number:
        try:
            data = urlencode({'To': phone_number, 'From': twilio_from, 'Body': body}).encode('utf-8')
            auth = base64.b64encode(f'{twilio_sid}:{twilio_token}'.encode()).decode('utf-8')
            request = Request(
                f'https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json',
                data=data,
                headers={
                    'Authorization': f'Basic {auth}',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                method='POST',
            )
            with urlopen(request, timeout=30):
                return True
        except Exception as exc:
            print(f'[auth-sms] Twilio send failed: {exc}')

    firebase_project = os.getenv('FIREBASE_PROJECT_ID')
    firebase_server_key = os.getenv('FIREBASE_SERVER_KEY')
    firebase_device_token = os.getenv('FIREBASE_DEVICE_TOKEN')
    if firebase_project and firebase_server_key and firebase_device_token:
        try:
            payload = {
                'message': {
                    'token': firebase_device_token,
                    'notification': {'title': 'Smart House Planner', 'body': body},
                    'data': {'type': 'otp', 'message': body},
                }
            }
            request = Request(
                f'https://fcm.googleapis.com/v1/projects/{firebase_project}/messages:send',
                data=json.dumps(payload).encode('utf-8'),
                headers={
                    'Authorization': f'key={firebase_server_key}',
                    'Content-Type': 'application/json',
                },
                method='POST',
            )
            with urlopen(request, timeout=30):
                return True
        except Exception as exc:
            print(f'[auth-sms] Firebase push failed: {exc}')

    print(f'[auth-sms] No configured SMS provider. OTP not sent to {phone_number}. Message: {body}')
    return False


def build_reset_url(token):
    base_url = os.getenv('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')
    return f'{base_url}/reset_password/{token}'


def _call_llm(messages):
    api_key = os.getenv('OPENAI_API_KEY')
    model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')

    if api_key:
        endpoint = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1/chat/completions')
        payload = {
            'model': model,
            'messages': messages,
            'temperature': 0.2,
        }
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }
        request = Request(endpoint, data=json.dumps(payload).encode('utf-8'), headers=headers)
        with urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
        choices = data.get('choices', [])
        if choices:
            return choices[0].get('message', {}).get('content', '').strip()
        return None

    azure_key = os.getenv('AZURE_OPENAI_API_KEY')
    azure_endpoint = os.getenv('AZURE_OPENAI_ENDPOINT')
    azure_deployment = os.getenv('AZURE_OPENAI_DEPLOYMENT')
    if azure_key and azure_endpoint and azure_deployment:
        api_version = os.getenv('AZURE_OPENAI_API_VERSION', '2024-02-01')
        endpoint = f"{azure_endpoint.rstrip('/')}/openai/deployments/{azure_deployment}/chat/completions?api-version={api_version}"
        payload = {
            'messages': messages,
            'temperature': 0.2,
        }
        headers = {
            'api-key': azure_key,
            'Content-Type': 'application/json',
        }
        request = Request(endpoint, data=json.dumps(payload).encode('utf-8'), headers=headers)
        with urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
        choices = data.get('choices', [])
        if choices:
            return choices[0].get('message', {}).get('content', '').strip()
        return None

    return None


class SupportConversationStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else SUPPORT_CHAT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text('{}', encoding='utf-8')

    def _read(self):
        try:
            content = self.path.read_text(encoding='utf-8').strip()
            data = json.loads(content) if content else {}
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data):
        self.path.write_text(json.dumps(data, indent=2), encoding='utf-8')

    def load(self, session_id):
        data = self._read()
        messages = data.get(str(session_id), [])
        if not isinstance(messages, list):
            return []
        return messages

    def append(self, session_id, message):
        data = self._read()
        session_key = str(session_id)
        messages = data.setdefault(session_key, [])
        if not isinstance(messages, list):
            messages = []
            data[session_key] = messages
        messages.append(message)
        self._write(data)
        return messages


class SupportTicketStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else SUPPORT_TICKETS_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text('[]', encoding='utf-8')

    def _read(self):
        try:
            content = self.path.read_text(encoding='utf-8').strip()
            data = json.loads(content) if content else []
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _write(self, data):
        self.path.write_text(json.dumps(data, indent=2), encoding='utf-8')

    def log(self, session_id, payload):
        tickets = self._read()
        ticket = {
            'id': str(uuid.uuid4()),
            'session_id': str(session_id),
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'payload': payload,
        }
        tickets.append(ticket)
        self._write(tickets)
        return tickets


def _ai_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ai_extract_area(question):
    match = re.search(r'(\d+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|square\s*feet|square\s*foot)', question.lower())
    return _ai_number(match.group(1)) if match else None


def _ai_extract_floors(question, default=1):
    match = re.search(r'(\d+)\s*(?:floor|floors|storey|storeys|मंजिल|मंज़िल)', question.lower())
    return int(match.group(1)) if match else default


def _ai_project_context(user_id):
    if not user_id:
        return {}
    try:
        store = get_project_store()
        projects = store.find_for_user(user_id) if hasattr(store, 'find_for_user') else []
        if not projects:
            return {}
        project = projects[0]
        return {
            'project_name': project.get('project_name', 'Untitled project'),
            'plot_length': project.get('plot_length'),
            'plot_width': project.get('plot_width'),
            'unit': project.get('unit', 'ft'),
            'built_up_area': project.get('built_up_area'),
            'floors': project.get('floors', 1),
            'rooms': project.get('rooms', {}),
            'room_dimensions': project.get('room_dimensions', {}),
            'roof_area': project.get('roof_area') or project.get('built_up_area'),
            'has_simulation': bool(project.get('simulation')),
        }
    except Exception:
        logger.exception('Unable to load saved project context')
        return {}


def _ai_intent(question):
    normalized = SupportAgent._normalize(question)
    for intent, aliases in AI_INTENT_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return intent
    return None


def _ai_calculator_context(question, project_context):
    normalized = SupportAgent._normalize(question)
    area = _ai_extract_area(question)
    floors = _ai_extract_floors(question, int(project_context.get('floors') or 1))
    if area is None:
        area = _ai_number(project_context.get('built_up_area'))
    context = {}
    local_answer = None
    intent = _ai_intent(question)

    if intent == 'materials' and area:
        result = calculate_materials(area, floors)
        context['calculator_result'] = {'calculator': 'calculate_materials', 'inputs': {'area': area, 'floors': floors}, 'outputs': result}
        local_answer = f"For {area:g} sq ft and {floors} floor(s), the app's preliminary material estimate is: cement {result['cement']:g}, sand {result['sand']:g}, aggregate {result['aggregate']:g}, bricks {result['bricks']:g}, steel {result['steel']:g}, flooring {result['flooring']:g}, and paint {result['paint']:g}. These are app estimates, not a purchase list."
    elif intent == 'cost' and area:
        result = _simulation_what_if({'built_up_area': area, 'floors': floors})
        context['calculator_result'] = {'calculator': '_simulation_what_if', 'inputs': {'built_up_area': area, 'floors': floors}, 'outputs': {'estimated_construction_cost': result['estimated_construction_cost']}}
        local_answer = f"For {area:g} sq ft and {floors} floor(s), the app's preliminary what-if construction estimate is ₹{result['estimated_construction_cost']:,.0f}. It uses built-up area × 140 + floors × 2,500; the /cost page instead sums costs entered by you and adds 5% contingency."
    elif intent == 'solar':
        usage_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:kwh|unit)', normalized)
        usage = _ai_number(usage_match.group(1)) if usage_match else 450
        result = _simulation_solar(usage, 400, 5)
        context['calculator_result'] = {'calculator': '_simulation_solar', 'inputs': {'monthly_usage': usage, 'wattage': 400, 'sunlight_hours': 5}, 'outputs': result}
        local_answer = f"Using the app's default assumptions of {usage:g} kWh/month, 400 W panels, and 5 sunlight hours, the preliminary solar estimate is {result['capacity_kw']:g} kW or {result['panels']} panel(s), generating about {result['monthly_generation_kwh']:g} kWh/month."
    elif intent == 'rainwater':
        roof_area = _ai_number(project_context.get('roof_area')) or area
        roof_area = roof_area or 1000
        result = _simulation_rainwater(roof_area, 1200, 0.8, 1800)
        context['calculator_result'] = {'calculator': '_simulation_rainwater', 'inputs': {'roof_area': roof_area, 'rainfall': 1200, 'runoff_coefficient': 0.8}, 'outputs': result}
        local_answer = f"Using roof area {roof_area:g} sq ft, 1,200 mm annual rainfall, and 0.8 runoff coefficient, the app estimates {result['estimated_water_collected']:,.0f} litres/year or {result['monthly_potential']:,.0f} litres/month. Replace the assumptions with local data for a better estimate."
    elif intent == 'cost' and re.search(r'\d+\s*(?:to|se|से)\s*\d+', normalized):
        values = re.findall(r'\d+(?:\.\d+)?', normalized)
        before, after = (_ai_number(values[0]), _ai_number(values[1])) if len(values) >= 2 else (None, None)
        if before and after:
            before_result = _simulation_what_if({'built_up_area': before, 'floors': floors})
            after_result = _simulation_what_if({'built_up_area': after, 'floors': floors})
            increase = after_result['estimated_construction_cost'] - before_result['estimated_construction_cost']
            context['calculator_result'] = {'calculator': '_simulation_what_if', 'inputs': {'before_area': before, 'after_area': after, 'floors': floors}, 'outputs': {'before_cost': before_result['estimated_construction_cost'], 'after_cost': after_result['estimated_construction_cost'], 'increase': increase}}
            local_answer = f"The app's what-if estimate changes from ₹{before_result['estimated_construction_cost']:,.0f} at {before:g} sq ft to ₹{after_result['estimated_construction_cost']:,.0f} at {after:g} sq ft, an indicative increase of ₹{increase:,.0f}."
    return context, local_answer


class SupportAgent:
    def __init__(self, knowledge=None):
        self.knowledge = knowledge or self._load_knowledge()

    @staticmethod
    def _normalize(text):
        return ' '.join((text or '').strip().lower().split())

    @staticmethod
    def _detect_language(text):
        normalized = SupportAgent._normalize(text)
        if any('\u0900' <= character <= '\u097f' for character in normalized):
            return 'hi'
        hinglish_markers = {'hai', 'ho', 'nahi', 'nahin', 'kar', 'kaise', 'chahiye', 'mera', 'meri', 'mein', 'par'}
        if hinglish_markers.intersection(set(normalized.split())):
            return 'hinglish'
        return 'en'

    @staticmethod
    def _localized_answer(faq, language):
        if language in {'hi', 'hinglish'}:
            localized = SUPPORT_LOCALIZED_ANSWERS.get(faq.get('category', 'general'), {}).get(language)
            if localized:
                return localized
        return faq.get('answer', 'I found a matching support answer.')

    def _load_knowledge(self):
        if SUPPORT_KNOWLEDGE_PATH.exists():
            try:
                content = SUPPORT_KNOWLEDGE_PATH.read_text(encoding='utf-8').strip()
                data = json.loads(content) if content else DEFAULT_SUPPORT_KNOWLEDGE
                if isinstance(data, dict) and isinstance(data.get('faqs'), list):
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        SUPPORT_KNOWLEDGE_PATH.write_text(json.dumps(DEFAULT_SUPPORT_KNOWLEDGE, indent=2), encoding='utf-8')
        return DEFAULT_SUPPORT_KNOWLEDGE

    def _save_knowledge(self):
        SUPPORT_KNOWLEDGE_PATH.write_text(json.dumps(self.knowledge, indent=2), encoding='utf-8')

    def train(self, question, answer, category='general'):
        question = (question or '').strip()
        answer = (answer or '').strip()
        if not question or not answer:
            raise ValueError('Both question and answer are required to train the support agent.')

        normalized = self._normalize(question)
        keywords = sorted({token for token in normalized.split() if len(token) > 2})
        self.knowledge.setdefault('faqs', []).append({
            'keywords': keywords,
            'answer': answer,
            'category': category.strip() or 'general'
        })
        self._save_knowledge()
        return {'status': 'trained', 'category': category.strip() or 'general', 'answer': answer}

    def _ask_llm(self, question, fallback_answer, project_context=None, calculator_context=None):
        if not (_has_openai_config() or _has_azure_config()):
            return None

        grounding = {
            'project_knowledge': VISHWAKARMA_PROJECT_KNOWLEDGE,
            'saved_project_context': project_context or {},
            'calculator_context': calculator_context or {},
        }
        messages = [
            {
                'role': 'system',
                'content': 'You are Vishwakarma AI, the project-specific assistant for VISHWAKARMA - Smart Building Constructor & Estimator. Use only the supplied project knowledge, saved project context, and calculator context for app-specific claims. Never invent routes, buttons, calculations, or features. If a requested feature is absent, say: This feature is not currently available in Vishwakarma. For structural, load-bearing, electrical, or construction-safety questions, provide educational estimates only and advise licensed professional verification. Reply in the same language or language mix used by the customer, including English, Hindi, or Hinglish. Keep answers concise and practical.'
            },
            {
                'role': 'user',
                'content': f"Customer question: {question}\n\nGrounding context:\n{json.dumps(grounding, ensure_ascii=False, default=str)}\n\nSuggested fallback answer: {fallback_answer}\n\nProvide a polished, grounded answer that helps the customer solve the issue."
            }
        ]

        try:
            return _call_llm(messages)
        except Exception:
            logger.exception('Vishwakarma AI provider request failed')
            return None

    def answer(self, question, user_id=None):
        normalized_question = self._normalize(question)
        if not normalized_question:
            return {'status': 'empty', 'answer': 'Please enter a question so the support agent can help you.', 'category': 'general', 'language': 'en'}

        language = self._detect_language(question)
        project_context = _ai_project_context(user_id)
        calculator_context, calculator_answer = _ai_calculator_context(question, project_context)
        intent = _ai_intent(question)

        best_match = None
        matched_keywords = []
        for faq in self.knowledge.get('faqs', []):
            aliases = SUPPORT_LANGUAGE_ALIASES.get(faq.get('category', 'general'), [])
            keywords = [str(item).strip().lower() for item in faq.get('keywords', []) + aliases if str(item).strip()]
            if not keywords:
                continue
            matches = [keyword for keyword in keywords if keyword in normalized_question]
            score = len(matches)
            if score > 0 and (best_match is None or score > best_match[0]):
                best_match = (score, faq, matches)

        intent_match = best_match and (intent is None or best_match[1].get('category') == intent or intent == 'planner' and best_match[1].get('category') == 'planner')
        if calculator_answer:
            response = {
                'status': 'calculated',
                'answer': calculator_answer,
                'category': intent or 'calculator',
                'matched_keywords': [],
                'language': language,
                'source': 'calculator',
            }
        elif intent in AI_LOCAL_ANSWERS and not intent_match:
            response = {
                'status': 'knowledge',
                'answer': AI_LOCAL_ANSWERS[intent],
                'category': intent,
                'matched_keywords': [],
                'language': language,
            }
        elif best_match:
            _, faq, matched_keywords = best_match
            response = {
                'status': 'matched',
                'answer': self._localized_answer(faq, language),
                'category': faq.get('category', 'general'),
                'matched_keywords': matched_keywords,
                'language': language,
            }
        else:
            response = {
                'status': 'fallback',
                'answer': SUPPORT_FALLBACK_ANSWERS.get(language, 'I could not find an exact match, but this app supports login, dashboard, project saving, report generation, 3D planner navigation, mobile/network use, and deployment checks. Please describe the issue and I can help narrow it down.'),
                'category': 'general',
                'matched_keywords': [],
                'language': language,
            }

        ai_answer = self._ask_llm(question, response['answer'], project_context, calculator_context)
        if ai_answer:
            response['answer'] = ai_answer
            response['source'] = 'ai'
        elif response.get('source') != 'calculator':
            response['source'] = 'knowledge'

        if project_context:
            response['project_context_used'] = project_context.get('project_name')
        if calculator_context:
            response['calculator_context'] = calculator_context.get('calculator_result', {}).get('calculator')

        return response


VishwakarmaAI = SupportAgent


class FileUserStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text('{}', encoding='utf-8')

    @staticmethod
    def _normalize_phone(value):
        return (value or '').strip()

    @staticmethod
    def _normalize_email(value):
        return (value or '').strip().lower()

    def _read(self):
        try:
            content = self.path.read_text(encoding='utf-8').strip()
            data = json.loads(content) if content else {}
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, users):
        self.path.write_text(json.dumps(users, indent=2, default=str), encoding='utf-8')

    def find_one(self, filters=None):
        if not isinstance(filters, dict):
            return None
        users = self._read()
        email_value = filters.get('email')
        if email_value is not None:
            record = users.get(self._normalize_email(email_value))
            if isinstance(record, dict):
                return record
        project_id = filters.get('_id')
        if project_id is not None:
            for user in users.values():
                if isinstance(user, dict) and str(user.get('_id') or user.get('id')) == str(project_id):
                    return user
        return None

    def insert_one(self, document):
        if not isinstance(document, dict):
            raise ValueError('Document must be a dictionary.')
        users = self._read()
        normalized_email = self._normalize_email(document.get('email'))
        if normalized_email and users.get(normalized_email):
            raise ValueError('An account with that email already exists.')
        user_id = str(document.get('_id') or document.get('id') or uuid.uuid4())
        role = str(document.get('role') or document.get('user_role') or 'user').strip().lower()
        if role not in {'admin', 'user'}:
            role = 'user'
        record = {
            '_id': user_id,
            'id': user_id,
            'name': str(document.get('name') or '').strip(),
            'email': normalized_email,
            'phone': self._normalize_phone(document.get('phone')),
            'password_hash': document.get('password_hash'),
            'role': role,
            'email_verified': bool(document.get('email_verified', False)),
            'mobile_verified': bool(document.get('mobile_verified', False)),
            'verification_codes': document.get('verification_codes', {}) or {},
            'reset_token': document.get('reset_token'),
            'reset_expires': document.get('reset_expires'),
            'created_at': document.get('created_at') or datetime.utcnow().isoformat(),
        }
        if normalized_email:
            users[normalized_email] = record
        self._write(users)
        return type('InsertOneResult', (), {'inserted_id': user_id})()

    def update_one(self, filters, update):
        if not isinstance(filters, dict) or not isinstance(update, dict):
            return {'matched_count': 0, 'modified_count': 0}
        record = self.find_one(filters)
        if not record:
            return {'matched_count': 0, 'modified_count': 0}
        update_data = update.get('$set', {}) if isinstance(update, dict) else {}
        for key, value in update_data.items():
            record[key] = value
        email_key = self._normalize_email(record.get('email'))
        users = self._read()
        if email_key:
            users[email_key] = record
            self._write(users)
        return {'matched_count': 1, 'modified_count': 1}

    def create_user(self, name, email, password_hash, phone=None, email_verified=False, mobile_verified=False, role='user'):
        users = self._read()
        normalized_email = self._normalize_email(email)
        if normalized_email and users.get(normalized_email):
            raise ValueError('An account with that email already exists.')
        user_id = str(uuid.uuid4())
        normalized_role = str(role or 'user').strip().lower()
        if normalized_role not in {'admin', 'user'}:
            normalized_role = 'user'
        record = {
            '_id': user_id,
            'id': user_id,
            'name': name.strip(),
            'email': normalized_email,
            'phone': self._normalize_phone(phone),
            'password_hash': password_hash,
            'role': normalized_role,
            'email_verified': bool(email_verified),
            'mobile_verified': bool(mobile_verified),
            'verification_codes': {},
            'reset_token': None,
            'reset_expires': None,
            'created_at': datetime.utcnow().isoformat(),
        }
        users[normalized_email] = record
        self._write(users)
        return record

    def find_by_email(self, email):
        users = self._read()
        return users.get((email or '').strip().lower())

    def verify_password(self, email, password):
        user = self.find_by_email(email)
        if user and check_password_hash(user['password_hash'], password):
            return user
        return None

    def create_reset_token(self, email):
        user = self.find_by_email(email)
        if not user:
            return None
        token = uuid.uuid4().hex
        user['reset_token'] = token
        user['reset_expires'] = (datetime.utcnow() + timedelta(minutes=30)).isoformat()
        users = self._read()
        users[(email or '').strip().lower()] = user
        self._write(users)
        reset_url = build_reset_url(token)
        send_email_message(
            email,
            'Reset your Smart House Planner password',
            f'Use the link below to reset your password:\n\n{reset_url}\n\nThis link expires in 30 minutes.'
        )
        return token

    def verify_reset_token(self, token):
        for user in self._read().values():
            if not isinstance(user, dict):
                continue
            if user.get('reset_token') == token and user.get('reset_expires'):
                try:
                    expires_at = datetime.fromisoformat(user['reset_expires'])
                    if expires_at > datetime.utcnow():
                        return user
                except ValueError:
                    pass
        return None

    def reset_password(self, token, new_password):
        user = self.verify_reset_token(token)
        if not user:
            return False
        users = self._read()
        stored_user = users.get(user['email'])
        if not stored_user:
            return False
        stored_user['password_hash'] = generate_password_hash(new_password)
        stored_user['reset_token'] = None
        stored_user['reset_expires'] = None
        users[stored_user['email']] = stored_user
        self._write(users)
        return True

    def issue_verification_code(self, email, channel):
        user = self.find_by_email(email)
        if not user:
            return None
        channel = (channel or 'email').lower()
        code = str(random.randint(100000, 999999))
        verification_codes = user.setdefault('verification_codes', {})
        verification_codes[channel] = {
            'code': code,
            'expires_at': (datetime.utcnow() + timedelta(minutes=15)).isoformat(),
        }
        users = self._read()
        users[(email or '').strip().lower()] = user
        self._write(users)

        delivered = False
        if channel == 'email':
            delivered = send_email_message(
                email,
                'Your Smart House Planner verification code',
                f'Your verification code is {code}. It expires in 15 minutes.'
            )
        elif channel in {'mobile', 'whatsapp'}:
            phone_number = (user.get('phone') or '').strip()
            if phone_number:
                delivered = send_sms_message(phone_number, f'Your Smart House Planner verification code is {code}. It expires in 15 minutes.', channel='whatsapp' if channel == 'whatsapp' else 'sms')

        return code if delivered else None

    def verify_verification_code(self, email, channel, code):
        user = self.find_by_email(email)
        if not user:
            return False
        channel = (channel or 'email').lower()
        record = (user.get('verification_codes') or {}).get(channel)
        if not record:
            return False
        try:
            expires_at = datetime.fromisoformat(record['expires_at'])
            if expires_at < datetime.utcnow():
                return False
        except (TypeError, ValueError):
            return False
        if str(record.get('code')) != str(code):
            return False
        user['mobile_verified' if channel == 'whatsapp' else f'{channel}_verified'] = True
        user['verification_codes'] = (user.get('verification_codes') or {})
        user['verification_codes'].pop(channel, None)
        users = self._read()
        users[(email or '').strip().lower()] = user
        self._write(users)
        return True


class FileProjectStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text('{}', encoding='utf-8')

    @staticmethod
    def _coerce_datetime(value):
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                return value
        return value

    def _read(self):
        try:
            content = self.path.read_text(encoding='utf-8').strip()
            data = json.loads(content) if content else {}
            if not isinstance(data, dict):
                return {}
            for user_projects in data.values():
                if isinstance(user_projects, list):
                    for item in user_projects:
                        if isinstance(item, dict):
                            item['created_at'] = self._coerce_datetime(item.get('created_at'))
                            item['updated_at'] = self._coerce_datetime(item.get('updated_at'))
            return data
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data):
        self.path.write_text(json.dumps(data, indent=2, default=str), encoding='utf-8')

    def _user_bucket(self, user_id):
        data = self._read()
        bucket = data.setdefault(str(user_id), [])
        if not isinstance(bucket, list):
            bucket = []
            data[str(user_id)] = bucket
        self._write(data)
        return bucket

    def insert_one(self, document):
        data = self._read()
        project_id = str(document.get('_id') or uuid.uuid4())
        doc = dict(document)
        doc['_id'] = project_id
        doc['id'] = project_id
        doc['created_at'] = doc.get('created_at') or datetime.utcnow().isoformat()
        doc['updated_at'] = doc.get('updated_at') or doc['created_at']
        bucket = data.setdefault(str(doc['user_id']), [])
        bucket.append(doc)
        self._write(data)
        return doc

    def find(self, filters=None):
        data = self._read()
        filters = filters or {}
        user_id = filters.get('user_id')
        items = data.get(str(user_id), []) if user_id is not None else []
        for item in items:
            if item.get('user_id') == user_id:
                yield item

    def find_one(self, filters):
        if not isinstance(filters, dict):
            return None
        user_id = filters.get('user_id')
        project_id = filters.get('_id')
        if user_id is None:
            return None
        for item in self._user_bucket(user_id):
            if str(item.get('_id')) == str(project_id):
                return item
        return None

    def update_one(self, filters, update):
        if not isinstance(filters, dict) or not isinstance(update, dict):
            return {'matched_count': 0, 'modified_count': 0}
        user_id = filters.get('user_id')
        project_id = filters.get('_id')
        if user_id is None and project_id is None:
            return {'matched_count': 0, 'modified_count': 0}
        data = self._read()
        bucket = data.get(str(user_id), []) if user_id is not None else []
        matched = False
        for item in bucket:
            if str(item.get('_id')) == str(project_id):
                matched = True
                for key, value in update.get('$set', {}).items():
                    item[key] = value
                item['updated_at'] = datetime.utcnow()
                break
        if matched:
            data[str(user_id)] = bucket
            self._write(data)
            return {'matched_count': 1, 'modified_count': 1}
        return {'matched_count': 0, 'modified_count': 0}

    def delete_one(self, filters):
        if not isinstance(filters, dict):
            return None
        user_id = filters.get('user_id')
        project_id = filters.get('_id')
        data = self._read()
        bucket = data.get(str(user_id), [])
        matched = [item for item in bucket if str(item.get('_id')) != str(project_id)]
        data[str(user_id)] = matched
        self._write(data)
        return {'deleted_count': len(bucket) - len(matched)}

    def find_for_user(self, user_id):
        data = self._read()
        items = data.get(str(user_id), [])
        normalized = []
        for item in items:
            if isinstance(item, dict):
                item['created_at'] = self._coerce_datetime(item.get('created_at'))
                item['updated_at'] = self._coerce_datetime(item.get('updated_at'))
                normalized.append(item)
        return sorted(normalized, key=lambda item: item.get('updated_at') or item.get('created_at') or datetime.min, reverse=True)


def _mongo_available():
    try:
        if mongo is None or not hasattr(mongo, 'cx'):
            return False
        mongo.cx.admin.command('ping')
        return True
    except Exception:
        return False


class MongoUserStore:
    def __init__(self, collection):
        self.collection = collection

    @staticmethod
    def _normalize_email(value):
        return (value or '').strip().lower()

    @staticmethod
    def _normalize_phone(value):
        return (value or '').strip()

    def find_one(self, filters=None):
        if not isinstance(filters, dict):
            return None
        email = filters.get('email')
        if email is not None:
            return self.collection.find_one({'email': self._normalize_email(email)})
        return self.collection.find_one(filters)

    def find_by_email(self, email):
        normalized_email = self._normalize_email(email)
        if not normalized_email:
            return None
        return self.collection.find_one({'email': normalized_email})

    def insert_one(self, document):
        if not isinstance(document, dict):
            raise ValueError('Document must be a dictionary.')
        email = self._normalize_email(document.get('email'))
        if email and self.collection.find_one({'email': email}):
            raise ValueError('An account with that email already exists.')
        doc = dict(document)
        doc['email'] = email
        if '_id' not in doc and 'id' in doc:
            doc['_id'] = doc['id']
        if '_id' not in doc:
            doc['_id'] = str(uuid.uuid4())
        doc.setdefault('verification_codes', {})
        doc.setdefault('reset_token', None)
        doc.setdefault('reset_expires', None)
        self.collection.insert_one(doc)
        return type('InsertOneResult', (), {'inserted_id': doc['_id']})()

    def update_one(self, filters, update):
        if not isinstance(filters, dict) or not isinstance(update, dict):
            return {'matched_count': 0, 'modified_count': 0}
        result = self.collection.update_one(filters, update)
        return {'matched_count': result.matched_count, 'modified_count': result.modified_count}

    def create_user(self, name, email, password_hash, phone=None, email_verified=False, mobile_verified=False, role='user'):
        normalized_email = self._normalize_email(email)
        if not normalized_email:
            raise ValueError('Email is required.')
        if self.find_by_email(normalized_email):
            raise ValueError('An account with that email already exists.')
        user_id = str(uuid.uuid4())
        normalized_role = str(role or 'user').strip().lower()
        if normalized_role not in {'admin', 'user'}:
            normalized_role = 'user'
        record = {
            '_id': user_id,
            'id': user_id,
            'name': str(name or '').strip(),
            'email': normalized_email,
            'phone': self._normalize_phone(phone),
            'password_hash': password_hash,
            'role': normalized_role,
            'email_verified': bool(email_verified),
            'mobile_verified': bool(mobile_verified),
            'verification_codes': {},
            'reset_token': None,
            'reset_expires': None,
            'created_at': datetime.utcnow().isoformat(),
        }
        self.collection.insert_one(record)
        return record

    def verify_password(self, email, password):
        user = self.find_by_email(email)
        if user and check_password_hash(user.get('password_hash', ''), password):
            return user
        return None

    def create_reset_token(self, email):
        user = self.find_by_email(email)
        if not user:
            return None
        token = uuid.uuid4().hex
        expires_at = (datetime.utcnow() + timedelta(minutes=30)).isoformat()
        self.collection.update_one({'_id': user.get('_id')}, {'$set': {'reset_token': token, 'reset_expires': expires_at}})
        send_email_message(
            email,
            'Reset your Smart House Planner password',
            f'Use the link below to reset your password:\n\n{build_reset_url(token)}\n\nThis link expires in 30 minutes.'
        )
        return token

    def verify_reset_token(self, token):
        user = self.collection.find_one({'reset_token': token})
        if not user or not user.get('reset_expires'):
            return None
        try:
            expires_at = datetime.fromisoformat(user['reset_expires'])
            if expires_at > datetime.utcnow():
                return user
        except ValueError:
            pass
        return None

    def reset_password(self, token, new_password):
        user = self.verify_reset_token(token)
        if not user:
            return False
        self.collection.update_one(
            {'_id': user.get('_id')},
            {'$set': {'password_hash': generate_password_hash(new_password), 'reset_token': None, 'reset_expires': None}}
        )
        return True

    def issue_verification_code(self, email, channel):
        user = self.find_by_email(email)
        if not user:
            return None
        channel = (channel or 'email').lower()
        code = str(random.randint(100000, 999999))
        verification_codes = dict(user.get('verification_codes') or {})
        verification_codes[channel] = {
            'code': code,
            'expires_at': (datetime.utcnow() + timedelta(minutes=15)).isoformat(),
        }
        self.collection.update_one({'_id': user.get('_id')}, {'$set': {'verification_codes': verification_codes}})

        delivered = False
        if channel == 'email':
            delivered = send_email_message(
                email,
                'Your Smart House Planner verification code',
                f'Your verification code is {code}. It expires in 15 minutes.'
            )
        elif channel in {'mobile', 'whatsapp'}:
            phone_number = self._normalize_phone(user.get('phone'))
            if phone_number:
                delivered = send_sms_message(phone_number, f'Your Smart House Planner verification code is {code}. It expires in 15 minutes.', channel='whatsapp' if channel == 'whatsapp' else 'sms')

            return code if delivered else None

    def verify_verification_code(self, email, channel, code):
        user = self.find_by_email(email)
        if not user:
            return False
        channel = (channel or 'email').lower()
        record = (user.get('verification_codes') or {}).get(channel)
        if not record:
            return False
        try:
            expires_at = datetime.fromisoformat(record['expires_at'])
            if expires_at < datetime.utcnow():
                return False
        except (TypeError, ValueError):
            return False
        if str(record.get('code')) != str(code):
            return False

        verification_codes = dict(user.get('verification_codes') or {})
        verification_codes.pop(channel, None)
        verified_field = 'mobile_verified' if channel == 'whatsapp' else f'{channel}_verified'
        self.collection.update_one(
            {'_id': user.get('_id')},
            {'$set': {verified_field: True, 'verification_codes': verification_codes}}
        )
        return True


def get_user_store():
    if _mongo_available():
        try:
            users = db_collection('users')
            if users is not None:
                return MongoUserStore(users)
        except Exception:
            pass
    return FileUserStore(USER_STORE_PATH)


def get_project_store():
    if _mongo_available():
        try:
            projects = db_collection('projects')
            if projects is not None:
                return projects
        except Exception:
            pass
    return FileProjectStore(PROJECT_STORE_PATH)


def _user_role_from_record(record):
    if not record:
        return 'user'
    role = str(record.get('role') or record.get('user_role') or 'user').strip().lower()
    return role if role in {'admin', 'user'} else 'user'


def _effective_admin_email_list():
    configured = os.getenv('ADMIN_EMAILS', 'admin@example.com')
    emails = []
    for email in str(configured).split(','):
        value = email.strip().lower()
        if value:
            emails.append(value)
    return emails


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login', next=request.path))

        users = get_user_store()
        record = None
        if hasattr(users, 'find_one'):
            record = users.find_one({'email': session.get('user_email')})
        elif hasattr(users, 'find_by_email'):
            record = users.find_by_email(session.get('user_email'))

        session_role = str(session.get('user_role') or _user_role_from_record(record)).strip().lower()
        if session_role != 'admin':
            flash('Admin access is required.', 'danger')
            return redirect(url_for('dashboard'))
        session['user_role'] = session_role
        return view(*args, **kwargs)
    return wrapped


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login', next=request.path))
        return view(*args, **kwargs)
    return wrapped


def db_collection(name):
    try:
        return getattr(mongo.db, name)
    except Exception:
        return None


def get_resource_repository(resource_type):
    if _mongo_available():
        collection = db_collection(resource_type)
        if collection is not None:
            return MongoResourceRepository(collection)
    return FileResourceRepository(RESOURCE_STORE_PATH)


def _resource_payload():
    payload = request.get_json(silent=True)
    if payload is None:
        payload = request.form.to_dict()
    return payload


@app.route('/api/<resource_type>', methods=['GET', 'POST'])
@login_required
def resource_collection_api(resource_type):
    if resource_type not in RESOURCE_SCHEMAS:
        return jsonify({'error': 'Unknown resource type.'}), 404
    repository = get_resource_repository(resource_type)
    user_id = session['user_id']
    if request.method == 'GET':
        items = repository.list(user_id, request.args.get('project_id'), resource_type)
        return jsonify({'items': [serialize_resource(item) for item in items], 'count': len(items)})

    try:
        document = validate_resource(resource_type, _resource_payload(), user_id, request.args.get('project_id'))
        item = repository.create(document)
        return jsonify({'item': serialize_resource(item)}), 201
    except ResourceValidationError as exc:
        return jsonify({'error': str(exc)}), 400
    except PyMongoError:
        return jsonify({'error': 'Database is unavailable.'}), 503


@app.route('/api/<resource_type>/<resource_id>', methods=['GET', 'PATCH', 'DELETE'])
@login_required
def resource_item_api(resource_type, resource_id):
    if resource_type not in RESOURCE_SCHEMAS:
        return jsonify({'error': 'Unknown resource type.'}), 404
    repository = get_resource_repository(resource_type)
    user_id = session['user_id']
    item = repository.get(user_id, resource_id, resource_type)
    if not item:
        return jsonify({'error': 'Resource not found.'}), 404
    if request.method == 'GET':
        return jsonify({'item': serialize_resource(item)})
    if request.method == 'DELETE':
        repository.delete(user_id, resource_id, resource_type)
        return '', 204

    try:
        current = serialize_resource(item) or {}
        current.update(_resource_payload())
        document = validate_resource(resource_type, current, user_id, current.get('project_id'))
        updated = repository.update(user_id, resource_id, document, resource_type)
        return jsonify({'item': serialize_resource(updated)})
    except ResourceValidationError as exc:
        return jsonify({'error': str(exc)}), 400
    except PyMongoError:
        return jsonify({'error': 'Database is unavailable.'}), 503


def safe_float(value, default=0):
    if value is None:
        return default
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
        if value.endswith('%'):
            value = value[:-1]
    try:
        number = float(value)
        return number if number >= 0 else default
    except (TypeError, ValueError):
        return default


def project_id_query(project_id):
    try:
        return {'_id': ObjectId(project_id)}
    except Exception:
        return {'_id': str(project_id)}


def calculate_materials(area, floors=1):
    return {key: round(area * factor * max(floors, 1), 2) for key, factor in MATERIAL_FACTORS.items()}


def _simulation_materials(area, floors=1, concrete_grade='M25', cement_grade='OPC 53', steel_grade='Fe500', brick_type='Fly Ash'):
    materials = calculate_materials(area, floors)
    concrete_multipliers = {'M20': 0.95, 'M25': 1.0, 'M30': 1.12, 'M35': 1.18}
    cement_multipliers = {'OPC 43': 0.96, 'OPC 53': 1.0, 'PSC': 0.98}
    steel_multipliers = {'Fe415': 0.96, 'Fe500': 1.0, 'Fe550': 1.08}
    brick_multipliers = {'Traditional': 0.96, 'Fly Ash': 1.0, 'AAC': 1.08}
    material_rates = {'cement': 0.18, 'sand': 0.05, 'aggregate': 0.06, 'bricks': 0.09, 'steel': 1.25, 'flooring': 0.12, 'paint': 0.08}

    adjusted_materials = {
        'cement': round(materials['cement'] * cement_multipliers.get(cement_grade, 1.0), 2),
        'sand': round(materials['sand'] * 1.04, 2),
        'aggregate': round(materials['aggregate'] * 1.06, 2),
        'bricks': round(materials['bricks'] * brick_multipliers.get(brick_type, 1.0), 2),
        'steel': round(materials['steel'] * steel_multipliers.get(steel_grade, 1.0), 2),
        'flooring': round(materials['flooring'] * 1.03, 2),
        'paint': round(materials['paint'] * 1.02, 2),
    }

    indicative_strength = round(min(95, max(40, (concrete_multipliers.get(concrete_grade, 1.0) * 45) + (steel_multipliers.get(steel_grade, 1.0) * 18) + (brick_multipliers.get(brick_type, 1.0) * 14) + max(floors, 1) * 4)), 1)
    estimated_material_cost = round(sum(adjusted_materials[key] * material_rates[key] for key in adjusted_materials), 2)
    durability_indicator = 'High' if indicative_strength >= 75 else 'Moderate' if indicative_strength >= 60 else 'Good'
    overall_result = 'Indicative / Educational Simulation'

    return {
        'area': round(area, 2),
        'floors': max(floors, 1),
        'material_quantities': adjusted_materials,
        'indicative_strength': f'{indicative_strength} MPa',
        'estimated_material_cost': round(estimated_material_cost, 2),
        'durability_indicator': durability_indicator,
        'overall_result': overall_result,
        'disclaimer': 'Educational Simulation — not a structural safety certification.'
    }


def _simulation_load(load_type='Live Load', load_value=50):
    load_value = max(0, safe_float(load_value, 0))
    normalized_type = str(load_type or 'Live Load').strip()
    load_aliases = {
        'live load': 'Live Load',
        'live': 'Live Load',
        'furniture': 'Furniture',
        'occupancy': 'Occupancy',
    }
    selected_type = load_aliases.get(normalized_type.lower(), normalized_type)
    if selected_type not in {'Live Load', 'Furniture', 'Occupancy'}:
        selected_type = 'Live Load'

    load_factor = {'Live Load': 1.0, 'Furniture': 0.85, 'Occupancy': 0.75}[selected_type]
    stress_score = round(min(100, max(0, load_value * load_factor * 0.7)), 1)
    if stress_score < 35:
        stress_level = 'Low'
    elif stress_score < 70:
        stress_level = 'Medium'
    else:
        stress_level = 'High'

    return {
        'load_type': selected_type,
        'load_value': round(load_value, 2),
        'stress_indicator': f'{stress_score}%',
        'stress_level': stress_level,
        'simulation_result': 'Educational Simulation — Not a Structural Safety Assessment',
        'building_visual_state': stress_level.lower(),
        'disclaimer': 'Educational Simulation — not a structural safety certification.'
    }


def _simulation_rainwater(roof_area=0, rainfall=0, runoff_coefficient=0.8, tank_capacity=0):
    roof_area = safe_float(roof_area, 0)
    rainfall = safe_float(rainfall, 0)
    runoff_coefficient = safe_float(runoff_coefficient, 0.8)
    tank_capacity = safe_float(tank_capacity, 0)

    annual_collection = roof_area * rainfall * runoff_coefficient
    monthly_potential = annual_collection / 12
    tank_status = 'Low' if tank_capacity <= 0 else 'Healthy' if monthly_potential >= tank_capacity else 'Moderate'

    return {
        'estimated_water_collected': round(annual_collection, 2),
        'monthly_potential': round(monthly_potential, 2),
        'tank_status': tank_status,
        'tank_capacity': round(tank_capacity, 2),
        'disclaimer': 'Educational Simulation — not a structural safety certification.'
    }


def _simulation_solar(monthly_usage=0, wattage=400, sunlight_hours=5, location='Location A'):
    monthly_usage = safe_float(monthly_usage, 0)
    wattage = safe_float(wattage, 400)
    sunlight_hours = safe_float(sunlight_hours, 5)
    capacity = monthly_usage / (30 * sunlight_hours * 0.8) if monthly_usage else 0
    panels = max(1, int(math.ceil((capacity * 1000) / wattage))) if capacity else 0
    daily_generation = round((panels * wattage * sunlight_hours * 0.8) / 1000, 2) if panels else 0
    monthly_generation = round(daily_generation * 30, 2) if daily_generation else 0

    return {
        'location': location,
        'capacity_kw': round(capacity, 2),
        'panels': panels,
        'daily_generation_kwh': daily_generation,
        'monthly_generation_kwh': monthly_generation,
        'disclaimer': 'Educational Simulation — not a solar engineering certification.'
    }


def _simulation_cost(payload):
    categories = [
        {'key': 'civil_work', 'label': 'Civil Work', 'base': 12000},
        {'key': 'materials', 'label': 'Materials', 'base': 18000},
        {'key': 'labour', 'label': 'Labour', 'base': 14000},
        {'key': 'electrical', 'label': 'Electrical', 'base': 5000},
        {'key': 'plumbing', 'label': 'Plumbing', 'base': 4000},
        {'key': 'flooring', 'label': 'Flooring', 'base': 5500},
        {'key': 'painting', 'label': 'Painting', 'base': 3600},
        {'key': 'doors_windows', 'label': 'Doors & Windows', 'base': 4200},
        {'key': 'other_expenses', 'label': 'Other Expenses', 'base': 2800},
    ]

    adjustments = {}
    if isinstance(payload, dict):
        adjustments = payload.get('adjustments', {}) or {}
        if not adjustments:
            for key in ('civil_work', 'materials', 'labour', 'electrical', 'plumbing', 'flooring', 'painting', 'doors_windows', 'other_expenses', 'cement', 'steel', 'bricks'):
                if key in payload:
                    adjustments[key] = payload.get(key)
        if not adjustments:
            for key, value in payload.items():
                if isinstance(value, (int, float, str)) and key not in {'project_name', 'area', 'floors'}:
                    adjustments[key] = value

    adjustment_map = {
        'civil_work': 'civil_work',
        'materials': 'materials',
        'labour': 'labour',
        'electrical': 'electrical',
        'plumbing': 'plumbing',
        'flooring': 'flooring',
        'painting': 'painting',
        'doors_windows': 'doors_windows',
        'doors-and-windows': 'doors_windows',
        'other_expenses': 'other_expenses',
        'other-expenses': 'other_expenses',
        'cement': 'materials',
        'steel': 'materials',
        'bricks': 'materials',
    }

    normalized_adjustments = {}
    for raw_key, raw_value in adjustments.items():
        key = str(raw_key).strip().lower().replace(' ', '_')
        mapped_key = adjustment_map.get(key, key)
        normalized_adjustments[mapped_key] = safe_float(raw_value, 0)

    breakdown = {}
    base_cost = 0
    for item in categories:
        adjustment = normalized_adjustments.get(item['key'], 0)
        adjusted_value = round(item['base'] * (1 + (adjustment / 100)), 2)
        breakdown[item['label']] = adjusted_value
        base_cost += adjusted_value

    material_cost = sum([breakdown['Materials'], breakdown['Flooring'], breakdown['Painting'], breakdown['Doors & Windows']])
    labour_cost = breakdown['Labour']
    contingency = round(base_cost * 0.05, 2)
    total_estimated_cost = round(base_cost + contingency, 2)

    return {
        'base_cost': round(base_cost, 2),
        'material_cost': round(material_cost, 2),
        'labour_cost': round(labour_cost, 2),
        'contingency': contingency,
        'total_estimated_cost': total_estimated_cost,
        'category_breakdown': breakdown,
        'disclaimer': 'Educational Simulation — preliminary planning estimate only.'
    }


def _simulation_what_if(payload):
    payload = payload or {}
    plot_length = safe_float(payload.get('plot_length'), 30)
    plot_width = safe_float(payload.get('plot_width'), 40)
    floors = int(safe_float(payload.get('floors'), 1) or 1)
    built_up_area = safe_float(payload.get('built_up_area'), plot_length * plot_width * 0.7 * floors)
    roof_area = safe_float(payload.get('roof_area'), plot_length * plot_width * 0.45)
    rainfall = safe_float(payload.get('rainfall'), 1200)
    solar_wattage = safe_float(payload.get('solar_wattage'), 400)
    sunlight_hours = safe_float(payload.get('sunlight_hours'), 6)
    monthly_usage = safe_float(payload.get('monthly_usage'), 1500)
    material_choice = payload.get('material_choice', 'Fly Ash')

    base_material_requirement = calculate_materials(built_up_area, floors)
    base_cost = round((built_up_area * 140) + (floors * 2500), 2)
    solar_capacity = _simulation_solar(monthly_usage, solar_wattage, sunlight_hours)
    rainwater = _simulation_rainwater(roof_area, rainfall, 0.8, 1800)

    return {
        'built_up_area': round(built_up_area, 2),
        'estimated_material_requirement': {key: round(value, 2) for key, value in base_material_requirement.items()},
        'estimated_construction_cost': base_cost,
        'solar_potential': {
            'capacity_kw': solar_capacity['capacity_kw'],
            'panels': solar_capacity['panels'],
            'monthly_generation_kwh': solar_capacity['monthly_generation_kwh']
        },
        'rainwater_potential': {
            'estimated_water_collected': rainwater['estimated_water_collected'],
            'monthly_potential': rainwater['monthly_potential'],
            'tank_status': rainwater['tank_status']
        },
        'material_choice': material_choice,
        'disclaimer': 'Indicative / Educational Simulation — not a professional design or approval.'
    }


@app.context_processor
def inject_globals():
    return {'rooms': ROOMS, 'now': datetime.utcnow()}


@app.route('/')
def home():
    return render_template('home.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/contact')
def contact():
    if request.method == 'POST':
        flash('Thanks. Your message has been noted for the project team.', 'success')
        return redirect(url_for('contact'))
    return render_template('contact.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if not name or '@' not in email or not phone or len(password) < 8 or password != confirm:
            flash('Enter a name, valid email, phone number, matching passwords, and a password of at least 8 characters.', 'danger')
        else:
            users = get_user_store()
            role = 'admin' if email.lower() in _effective_admin_email_list() else 'user'
            try:
                if hasattr(users, 'find_one'):
                    if users.find_one({'email': email}):
                        flash('An account with that email already exists.', 'warning')
                        return render_template('auth.html', mode='register')
                    result = users.insert_one({
                        'name': name,
                        'email': email,
                        'phone': phone,
                        'password_hash': generate_password_hash(password),
                        'role': role,
                        'email_verified': verification_providers_configured() is False,
                        'mobile_verified': verification_providers_configured() is False,
                        'verification_codes': {},
                        'created_at': datetime.utcnow(),
                    })
                    session['user_id'], session['user_name'], session['user_email'], session['user_role'] = str(result.inserted_id), name, email, role
                else:
                    if users.find_by_email(email):
                        flash('An account with that email already exists.', 'warning')
                        return render_template('auth.html', mode='register')
                    created = users.create_user(name, email, generate_password_hash(password), phone=phone, email_verified=not verification_providers_configured(), mobile_verified=not verification_providers_configured(), role=role)
                    session['user_id'], session['user_name'], session['user_email'], session['user_role'] = str(created['_id']), created['name'], created['email'], created.get('role', 'user')
                if verification_providers_configured():
                    flash('Your account is created. Please verify your email or mobile number to continue.', 'success')
                    return redirect(url_for('verify_account'))
                flash('Account ready. You can continue to your dashboard.', 'success')
                return redirect(url_for('dashboard'))
            except (PyMongoError, ValueError):
                flash('Database is unavailable. Start MongoDB, then try registering again.', 'danger')
    return render_template('auth.html', mode='register')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        users = get_user_store()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        try:
            if hasattr(users, 'find_one'):
                record = users.find_one({'email': email})
            else:
                record = users.find_by_email(email)
            if record and check_password_hash(record['password_hash'], password):
                session['user_id'], session['user_name'], session['user_email'] = str(record.get('_id') or record.get('id')), record['name'], record.get('email') or email
                session['user_role'] = _user_role_from_record(record)
                if not (record.get('email_verified') or record.get('mobile_verified')) and verification_providers_configured():
                    flash('Please verify your email or mobile number before logging in.', 'warning')
                    return redirect(url_for('verify_account'))
                if not (record.get('email_verified') or record.get('mobile_verified')):
                    if hasattr(users, 'update_one'):
                        users.update_one({'_id': record.get('_id') or record.get('id')}, {'$set': {'email_verified': True, 'mobile_verified': True}})
                    elif hasattr(users, 'find_by_email'):
                        current = users.find_by_email(email)
                        if current:
                            current['email_verified'] = True
                            current['mobile_verified'] = True
                            users._write({**users._read(), (email or '').strip().lower(): current})
                return redirect(request.args.get('next') or url_for('dashboard'))
            flash('Email or password is incorrect.', 'danger')
        except PyMongoError:
            flash('Database is unavailable. Start MongoDB, then try logging in again.', 'danger')
    return render_template('auth.html', mode='login')


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        users = get_user_store()
        try:
            if hasattr(users, 'find_one'):
                record = users.find_one({'email': email})
            else:
                record = users.find_by_email(email)
            if record and hasattr(users, 'create_reset_token'):
                token = users.create_reset_token(email)
                if token:
                    flash('Password reset link is ready. Use the reset token in the app to set a new password.', 'success')
                    return redirect(url_for('reset_password', token=token))
            flash('If that email exists in our records, a reset request has been generated.', 'info')
            return render_template('auth.html', mode='forgot_password')
        except PyMongoError:
            flash('Database is unavailable. Please try again later.', 'danger')
    return render_template('auth.html', mode='forgot_password')


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = None
    users = get_user_store()
    if hasattr(users, 'verify_reset_token'):
        user = users.verify_reset_token(token)
    if not user:
        flash('This reset link is invalid or expired. Please request a new one.', 'danger')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        if len(new_password) < 8 or new_password != confirm_password:
            flash('Enter a new password with at least 8 characters and confirm it correctly.', 'danger')
            return render_template('auth.html', mode='reset_password', token=token)
        if hasattr(users, 'reset_password'):
            if users.reset_password(token, new_password):
                flash('Your password was updated successfully. Please log in again.', 'success')
                return redirect(url_for('login'))
        flash('Unable to reset password right now.', 'danger')
    return render_template('auth.html', mode='reset_password', token=token)


@app.route('/verify_account', methods=['GET', 'POST'])
def verify_account():
    user_email = session.get('user_email')
    users = get_user_store()
    record = None
    if user_email:
        if hasattr(users, 'find_one'):
            record = users.find_one({'email': user_email})
        else:
            record = users.find_by_email(user_email)

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower() or user_email
        method = request.form.get('method', 'email')
        action = request.form.get('action', 'verify')
        if not email:
            flash('Enter your email address to verify your account.', 'danger')
            return render_template('auth.html', mode='verify_account', user_email=user_email)

        record = users.find_one({'email': email}) if hasattr(users, 'find_one') else users.find_by_email(email)
        if not record:
            flash('No account was found for that email.', 'warning')
            return render_template('auth.html', mode='verify_account', user_email=email)

        if action == 'send':
            if hasattr(users, 'issue_verification_code'):
                code = users.issue_verification_code(email, method)
                if code:
                    flash(f'A verification code for {method} has been generated: {code}.', 'success')
                else:
                    flash('Unable to generate a verification code.', 'danger')
            else:
                flash('Verification is not available for this account store.', 'warning')
            return render_template('auth.html', mode='verify_account', user_email=email)

        code = request.form.get('code', '').strip()
        if hasattr(users, 'verify_verification_code'):
            if users.verify_verification_code(email, method, code):
                session['user_id'], session['user_name'], session['user_email'] = str(record.get('_id') or record.get('id')), record['name'], record.get('email')
                flash(f'{method.title()} verified successfully.', 'success')
                return redirect(request.args.get('next') or url_for('dashboard'))
            flash('That verification code is invalid or expired.', 'danger')
        else:
            flash('Verification is not available for this account store.', 'warning')

    if record and not (record.get('email_verified') or record.get('mobile_verified')):
        if user_email:
            session['user_email'] = user_email
        return render_template('auth.html', mode='verify_account', user_email=user_email or record.get('email'))
    if record:
        return redirect(url_for('dashboard'))
    return render_template('auth.html', mode='verify_account', user_email=user_email)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route('/dashboard')
@login_required
def dashboard():
    projects = get_project_store()
    if hasattr(projects, 'find_for_user'):
        all_projects = projects.find_for_user(session['user_id'])
        recent = all_projects[:5]
    elif hasattr(projects, 'find'):
        all_projects = list(projects.find({'user_id': session['user_id']}).sort('updated_at', -1))
        recent = all_projects[:5]
    else:
        all_projects = []
        recent = []

    total_projects = len(all_projects)
    total_built_area = round(sum(float(item.get('built_up_area', 0) or 0) for item in all_projects), 2)
    total_cost = round(sum(float(item.get('material_estimate', {}).get('cement', 0) or 0) for item in all_projects) * 0.5 + total_built_area * 75, 2)
    solar_output = round(total_built_area * 0.08, 2)
    water_potential = round(total_built_area * 0.12, 2)
    resource_metrics = {}
    for resource_type in RESOURCE_SCHEMAS:
        resource_metrics[resource_type] = len(get_resource_repository(resource_type).list(session['user_id'], resource_type=resource_type))
    expense_items = get_resource_repository('expenses').list(session['user_id'], resource_type='expenses')
    invoice_items = get_resource_repository('invoices').list(session['user_id'], resource_type='invoices')
    expenses_total = round(sum(float(item.get('amount', 0) or 0) for item in expense_items), 2)
    invoices_total = round(sum(float(item.get('amount', 0) or 0) for item in invoice_items), 2)
    last_updated = recent[0].get('updated_at') if recent else None
    last_updated_label = last_updated.strftime('%d %b %Y') if getattr(last_updated, 'strftime', None) else 'No project yet'
    avg_area = round(total_built_area / total_projects, 2) if total_projects else 0

    dashboard_stats = {
        'projects': total_projects,
        'tools': len(RESOURCE_SCHEMAS),
        'coverage': 70,
        'area_total': total_built_area,
        'avg_area': avg_area,
        'last_updated': last_updated_label,
        'total_cost': f'₹{total_cost:,.0f}',
        'solar_output': f'{solar_output:,.0f} kWh',
        'water_potential': f'{water_potential:,.0f} L',
        'labour': resource_metrics['labour'],
        'materials': resource_metrics['materials'],
        'equipment': resource_metrics['equipment'],
        'tasks': resource_metrics['tasks'],
        'expenses': expenses_total,
        'invoices': invoices_total,
    }

    return render_template('dashboard.html', recent=recent, total=total_projects, metrics=dashboard_stats)


@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    users = get_user_store()
    user_records = []
    if hasattr(users, '_read'):
        raw_users = users._read()
        if isinstance(raw_users, dict):
            user_records = list(raw_users.values())
        elif isinstance(raw_users, list):
            user_records = raw_users
        total_users = len(user_records)
    else:
        total_users = 0

    projects = get_project_store()
    all_projects = []
    if hasattr(projects, 'find_for_user'):
        for user in user_records:
            if not isinstance(user, dict):
                continue
            user_id = str(user.get('_id') or user.get('id') or '').strip()
            if user_id:
                all_projects.extend(projects.find_for_user(user_id))

    return render_template('admin.html', total_users=total_users, total_projects=len(all_projects), users=user_records if user_records else [])


@app.route('/planner', methods=['GET', 'POST'])
@login_required
def planner():
    result = None
    project = None
    project_id = request.args.get('project_id')
    if project_id:
        for collection in (get_project_store(), FileProjectStore(PROJECT_STORE_PATH)):
            if hasattr(collection, 'find_one'):
                project = collection.find_one({'user_id': session['user_id'], **project_id_query(project_id)})
                if project:
                    break

    if request.method == 'POST':
        length, width = safe_float(request.form.get('plot_length')), safe_float(request.form.get('plot_width'))
        floors = int(safe_float(request.form.get('floors'), 1) or 1)
        if not length or not width:
            flash('Plot dimensions must be greater than zero.', 'danger')
        else:
            area = length * width
            coverage = min(area * 0.7, area)
            selected = {room: int(safe_float(request.form.get('room_' + room), 0)) for room in ROOMS if safe_float(request.form.get('room_' + room), 0) > 0}
            room_dimensions = {}
            for room in ROOMS:
                width_value = safe_float(request.form.get(f'room_width_{room}'), ROOM_DIMENSIONS.get(room, {}).get('width', 12))
                depth_value = safe_float(request.form.get(f'room_depth_{room}'), ROOM_DIMENSIONS.get(room, {}).get('depth', 10))
                room_dimensions[room] = {
                    'width': round(width_value, 1) if width_value else round(ROOM_DIMENSIONS.get(room, {}).get('width', 12), 1),
                    'depth': round(depth_value, 1) if depth_value else round(ROOM_DIMENSIONS.get(room, {}).get('depth', 10), 1),
                }
            result = {'length': length, 'width': width, 'unit': request.form.get('unit', 'ft'), 'floors': floors, 'area': round(area, 2), 'built_up': round(coverage * floors, 2), 'open_area': round(area - coverage, 2), 'selected': selected, 'room_dimensions': room_dimensions}
            if request.form.get('save_project'):
                projects = get_project_store()
                if projects is not None:
                    project_data = {
                        'user_id': session['user_id'],
                        'project_name': request.form.get('project_name', 'Untitled plan'),
                        'plot_length': length,
                        'plot_width': width,
                        'unit': result['unit'],
                        'floors': floors,
                        'rooms': selected,
                        'room_dimensions': room_dimensions,
                        'built_up_area': result['built_up'],
                        'layout_data': {},
                        'material_estimate': calculate_materials(result['built_up'], floors),
                        'created_at': datetime.utcnow(),
                        'updated_at': datetime.utcnow(),
                        'team_members': [],
                        'comments': [],
                        'versions': [{
                            'plot_length': length,
                            'plot_width': width,
                            'unit': result['unit'],
                            'floors': floors,
                            'rooms': selected,
                            'room_dimensions': room_dimensions,
                            'built_up_area': result['built_up'],
                            'created_at': datetime.utcnow()
                        }]
                    }
                    if hasattr(projects, 'insert_one'):
                        projects.insert_one(project_data)
                        flash('Project saved with version history.', 'success')
    elif project:
        result = {
            'length': project.get('plot_length', 30),
            'width': project.get('plot_width', 40),
            'unit': project.get('unit', 'ft'),
            'floors': project.get('floors', 1),
            'area': project.get('plot_length', 30) * project.get('plot_width', 40),
            'built_up': project.get('built_up_area', 0),
            'open_area': max(0.0, (project.get('plot_length', 30) * project.get('plot_width', 40)) - project.get('built_up_area', 0)),
            'selected': project.get('rooms', {}) or {},
            'room_dimensions': project.get('room_dimensions', {}) or {}
        }

    return render_template('planner.html', result=result, project=project)


@app.route('/materials', methods=['GET', 'POST'])
@login_required
def materials():
    area = safe_float(request.form.get('built_up_area')) if request.method == 'POST' else 0
    estimate = calculate_materials(area, int(safe_float(request.form.get('floors'), 1) or 1)) if area else None
    return render_template('materials.html', estimate=estimate, area=area)


@app.route('/cost', methods=['GET', 'POST'])
@login_required
def cost():
    categories = ['Civil work', 'Materials', 'Labour', 'Electrical', 'Plumbing', 'Flooring', 'Painting', 'Doors and windows', 'Other expenses']
    values = {item: safe_float(request.form.get('cost_' + item)) for item in categories} if request.method == 'POST' else {}
    subtotal = sum(values.values())
    contingency = subtotal * 0.05
    return render_template('cost.html', categories=categories, values=values, subtotal=subtotal, contingency=contingency, total=subtotal + contingency)


@app.route('/solar', methods=['GET', 'POST'])
@login_required
def solar():
    result = None
    if request.method == 'POST':
        monthly, roof, sun = safe_float(request.form.get('monthly')), safe_float(request.form.get('roof_area')), safe_float(request.form.get('sun_hours'))
        watt = safe_float(request.form.get('wattage'), 400)
        if monthly and roof and sun:
            capacity = monthly / (30 * sun * 0.8)
            result = {'capacity': round(capacity, 2), 'panels': int(-(-capacity * 1000 // watt)), 'yearly': round(capacity * sun * 365 * 0.8, 2)}
    return render_template('solar.html', result=result)


@app.route('/rainwater', methods=['GET', 'POST'])
@login_required
def rainwater():
    result = None
    if request.method == 'POST':
        roof, rainfall, coefficient = safe_float(request.form.get('roof_area')), safe_float(request.form.get('rainfall')), safe_float(request.form.get('coefficient'), 0.8)
        result = round(roof * rainfall * coefficient, 2) if roof and rainfall else None
    return render_template('rainwater.html', result=result)


@app.route('/simulation')
def simulation():
    projects = []
    if session.get('user_id'):
        collection = get_project_store()
        if hasattr(collection, 'find_for_user'):
            projects = collection.find_for_user(session['user_id'])
    return render_template('simulation.html', projects=projects)


@app.route('/api/simulation/material', methods=['POST'])
def simulation_material_api():
    payload = request.get_json(silent=True) or {}
    area = safe_float(payload.get('area'), 0)
    floors = int(safe_float(payload.get('floors'), 1) or 1)
    if not area:
        return jsonify({'error': 'Area must be greater than zero.'}), 400

    result = _simulation_materials(
        area=area,
        floors=floors,
        concrete_grade=payload.get('concrete_grade', 'M25'),
        cement_grade=payload.get('cement_grade', 'OPC 53'),
        steel_grade=payload.get('steel_grade', 'Fe500'),
        brick_type=payload.get('brick_type', 'Fly Ash')
    )
    return jsonify(result)


@app.route('/api/simulation/load', methods=['POST'])
def simulation_load_api():
    payload = request.get_json(silent=True) or {}
    return jsonify(_simulation_load(payload.get('load_type', 'Live Load'), payload.get('load_value', 50)))


@app.route('/api/simulation/rainwater', methods=['POST'])
def simulation_rainwater_api():
    payload = request.get_json(silent=True) or {}
    return jsonify(_simulation_rainwater(payload.get('roof_area', 0), payload.get('rainfall', 0), payload.get('runoff_coefficient', 0.8), payload.get('tank_capacity', 0)))


@app.route('/api/simulation/solar', methods=['POST'])
def simulation_solar_api():
    payload = request.get_json(silent=True) or {}
    return jsonify(_simulation_solar(payload.get('monthly_usage', 0), payload.get('wattage', 400), payload.get('sunlight_hours', 5), payload.get('location', 'Location A')))


@app.route('/api/simulation/cost', methods=['POST'])
def simulation_cost_api():
    payload = request.get_json(silent=True) or {}
    return jsonify(_simulation_cost(payload))


@app.route('/api/simulation/what-if', methods=['POST'])
def simulation_what_if_api():
    payload = request.get_json(silent=True) or {}
    return jsonify(_simulation_what_if(payload))


@app.route('/api/simulation/save', methods=['POST'])
def simulation_save_api():
    if 'user_id' not in session:
        return jsonify({'error': 'Please log in to save a simulation.'}), 401

    payload = request.get_json(silent=True) or {}
    project_id = payload.get('project_id')
    outcome = payload.get('outcome') or {}

    if not project_id:
        return jsonify({'error': 'Choose a project to save this simulation.'}), 400

    collection = get_project_store()
    if not hasattr(collection, 'find_one'):
        return jsonify({'error': 'Project storage is unavailable.'}), 500

    project = collection.find_one({'user_id': session['user_id'], **project_id_query(project_id)})
    if not project:
        return jsonify({'error': 'Project not found.'}), 404

    project['simulation'] = {
        'saved_at': datetime.utcnow(),
        'result': outcome
    }
    collection.update_one({'user_id': session['user_id'], **project_id_query(project_id)}, {'$set': {'simulation': project['simulation']}})

    return jsonify({'success': True, 'message': 'Simulation saved to project.'})


@app.route('/api/simulation/export', methods=['POST'])
def simulation_export_api():
    payload = request.get_json(silent=True) or {}
    summary = payload.get('summary') or payload.get('results') or payload or {}

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4)
    y = 790

    pdf.setTitle('Construction Simulation Report')
    pdf.setFont('Helvetica-Bold', 18)
    pdf.drawString(50, y, 'Construction Simulation Lab Report')
    y -= 28
    pdf.setFont('Helvetica', 11)
    pdf.drawString(50, y, f"Generated: {datetime.utcnow().strftime('%d %b %Y %H:%M UTC')}")
    y -= 26

    lines = [
        'This report is educational and indicative only.',
        '',
    ]

    if isinstance(summary, dict):
        for key, value in summary.items():
            label = key.replace('_', ' ').title()
            if isinstance(value, dict):
                for nested_key, nested_value in value.items():
                    lines.append(f"{label} - {nested_key}: {nested_value}")
            else:
                lines.append(f"{label}: {value}")
    else:
        lines.append(str(summary))

    for line in lines:
        if y < 60:
            pdf.showPage(); y = 790
        pdf.drawString(50, y, line[:110])
        y -= 18

    pdf.save()
    stream.seek(0)
    return send_file(stream, as_attachment=True, download_name='construction-simulation-report.pdf', mimetype='application/pdf')


@app.route('/projects')
@login_required
def projects():
    collection = get_project_store()
    if hasattr(collection, 'find_for_user'):
        items = collection.find_for_user(session['user_id'])
    elif hasattr(collection, 'find'):
        items = list(collection.find({'user_id': session['user_id']}).sort('updated_at', -1))
    else:
        items = []
    return render_template('projects.html', projects=items)


@app.route('/projects/<project_id>')
@login_required
def project_detail(project_id):
    collection = get_project_store()
    if hasattr(collection, 'find_one'):
        filters = {'user_id': session['user_id'], **project_id_query(project_id)}
        project = collection.find_one(filters)
    else:
        project = None
    if not project:
        return render_template('error.html', code=404, message='Project not found.'), 404
    return render_template('project_detail.html', project=project)


@app.route('/projects/<project_id>/delete', methods=['POST'])
@login_required
def delete_project(project_id):
    collection = get_project_store()
    if hasattr(collection, 'delete_one'):
        collection.delete_one({'user_id': session['user_id'], **project_id_query(project_id)})
    flash('Project deleted.', 'success')
    return redirect(url_for('projects'))


@app.route('/projects/<project_id>/report')
@login_required
def report(project_id):
    collection = get_project_store()
    if hasattr(collection, 'find_one'):
        project = collection.find_one({'user_id': session['user_id'], **project_id_query(project_id)})
    else:
        project = None
    if not project:
        return render_template('error.html', code=404, message='Project not found.'), 404
    return render_template('report.html', project=project)


@app.route('/projects/<project_id>/report.pdf')
@login_required
def report_pdf(project_id):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    collection = get_project_store()
    if hasattr(collection, 'find_one'):
        project = collection.find_one({'user_id': session['user_id'], **project_id_query(project_id)})
    else:
        project = None
    if not project:
        return render_template('error.html', code=404, message='Project not found.'), 404
    stream = io.BytesIO(); pdf = canvas.Canvas(stream, pagesize=A4); y = 800
    pdf.setTitle('Smart House Construction Planner Report')
    pdf.setFont('Helvetica-Bold', 18); pdf.drawString(50, y, 'Smart House & Construction Planner'); y -= 30
    pdf.setFont('Helvetica', 11)
    lines = [f"Project: {project.get('project_name', 'Untitled')}", f"Prepared for: {session.get('user_name', '')}", f"Plot: {project.get('plot_length')} x {project.get('plot_width')} {project.get('unit', 'ft')}", f"Floors: {project.get('floors')}", f"Built-up area: {project.get('built_up_area')} sq units", '', 'Preliminary, approximate estimate only. Consult licensed professionals and local authorities.']
    for line in lines: pdf.drawString(50, y, line); y -= 22
    pdf.save(); stream.seek(0)
    return send_file(stream, as_attachment=True, download_name='house-planner-report.pdf', mimetype='application/pdf')


@app.route('/project/<project_id>/team', methods=['GET', 'POST'])
@login_required
def project_team(project_id):
    collection = get_project_store()
    project = collection.find_one({'user_id': session['user_id'], **project_id_query(project_id)}) if hasattr(collection, 'find_one') else None
    
    if not project:
        flash('Project not found.', 'danger')
        return redirect(url_for('projects'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        role = request.form.get('role', 'collaborator')
        
        if not project.get('team_members'):
            project['team_members'] = []
        
        if email not in [m.get('email') for m in project['team_members']]:
            project['team_members'].append({'email': email, 'role': role, 'added_at': datetime.utcnow()})
            collection.update_one({'user_id': session['user_id'], **project_id_query(project_id)}, {'$set': {'team_members': project['team_members']}})
            flash(f'{email} added to team as {role}.', 'success')
        else:
            flash('Team member already exists.', 'warning')
    
    return render_template('project_team.html', project=project)


@app.route('/project/<project_id>/comments', methods=['GET', 'POST'])
@login_required
def project_comments(project_id):
    collection = get_project_store()
    project = collection.find_one({'user_id': session['user_id'], **project_id_query(project_id)}) if hasattr(collection, 'find_one') else None
    
    if not project:
        flash('Project not found.', 'danger')
        return redirect(url_for('projects'))
    
    if request.method == 'POST':
        comment_text = request.form.get('comment', '').strip()
        if comment_text:
            if not project.get('comments'):
                project['comments'] = []
            
            project['comments'].append({
                'author': session.get('user_name', 'Anonymous'),
                'text': comment_text,
                'created_at': datetime.utcnow()
            })
            collection.update_one({'user_id': session['user_id'], **project_id_query(project_id)}, {'$set': {'comments': project['comments']}})
            flash('Comment added.', 'success')
    
    return render_template('project_comments.html', project=project, comments=project.get('comments', []))


@app.route('/project/<project_id>/share', methods=['GET', 'POST'])
@login_required
def project_share(project_id):
    collection = get_project_store()
    project = collection.find_one({'user_id': session['user_id'], **project_id_query(project_id)}) if hasattr(collection, 'find_one') else None
    
    if not project:
        flash('Project not found.', 'danger')
        return redirect(url_for('projects'))
    
    if request.method == 'POST':
        if request.form.get('generate_link'):
            share_token = str(uuid.uuid4())
            collection.update_one({'user_id': session['user_id'], **project_id_query(project_id)}, {'$set': {'share_token': share_token}})
            share_url = request.base_url.replace('/share', '') + '?share=' + share_token
            flash(f'Share link generated: {share_url}', 'success')
            project['share_token'] = share_token
        
        elif request.form.get('recipient_email'):
            recipient = request.form.get('recipient_email', '').strip()
            message = request.form.get('message', 'Check out my project!')
            flash(f'Project sharing email would be sent to {recipient} with message: {message}', 'info')
    
    return render_template('project_share.html', project=project)


@app.route('/project/<project_id>/milestones', methods=['GET', 'POST'])
@login_required
def project_milestones(project_id):
    collection = get_project_store()
    project = collection.find_one({'user_id': session['user_id'], **project_id_query(project_id)}) if hasattr(collection, 'find_one') else None

    if not project:
        flash('Project not found.', 'danger')
        return redirect(url_for('projects'))

    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        if title:
            milestones = project.get('milestones') or []
            milestone = {
                '_id': str(uuid.uuid4()),
                'title': title,
                'status': (request.form.get('status') or 'planned').strip(),
                'due_date': (request.form.get('due_date') or '').strip(),
                'notes': (request.form.get('notes') or '').strip(),
                'created_at': datetime.utcnow().isoformat()
            }
            milestones.append(milestone)
            collection.update_one({'user_id': session['user_id'], **project_id_query(project_id)}, {'$set': {'milestones': milestones}})
            project['milestones'] = milestones
            flash('Milestone added successfully.', 'success')
            return redirect(url_for('project_milestones', project_id=project_id))
        flash('Please enter a milestone title.', 'warning')

    return render_template('project_milestones.html', project=project, milestones=project.get('milestones', []))


@app.route('/project/<project_id>/alternatives', methods=['GET', 'POST'])
@login_required
def project_alternatives(project_id):
    collection = get_project_store()
    project = collection.find_one({'user_id': session['user_id'], **project_id_query(project_id)}) if hasattr(collection, 'find_one') else None

    if not project:
        flash('Project not found.', 'danger')
        return redirect(url_for('projects'))

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        if name:
            materials_cost = float(request.form.get('materials_cost', 0) or 0)
            labour_cost = float(request.form.get('labour_cost', 0) or 0)
            other_cost = float(request.form.get('other_cost', 0) or 0)
            built_up_area = float(request.form.get('built_up_area', project.get('built_up_area', 0)) or 0)
            alternative = {
                '_id': str(uuid.uuid4()),
                'name': name,
                'description': (request.form.get('description') or '').strip(),
                'built_up_area': built_up_area,
                'materials_cost': materials_cost,
                'labour_cost': labour_cost,
                'other_cost': other_cost,
                'status': (request.form.get('status') or 'concept').strip(),
                'total_cost': round(materials_cost + labour_cost + other_cost, 2),
                'created_at': datetime.utcnow().isoformat()
            }
            alternatives = list(project.get('design_alternatives') or [])
            alternatives.append(alternative)
            collection.update_one({'user_id': session['user_id'], **project_id_query(project_id)}, {'$set': {'design_alternatives': alternatives}})
            project['design_alternatives'] = alternatives
            flash('Design alternative saved.', 'success')
            return redirect(url_for('project_alternatives', project_id=project_id))
        flash('Please provide an alternative name.', 'warning')

    alternatives = project.get('design_alternatives') or []
    recommended = next((alt for alt in alternatives if (alt.get('status') or '').lower() == 'recommended'), alternatives[0] if alternatives else None)
    chart_max = max((float(alt.get('total_cost', 0) or 0) for alt in alternatives), default=0)
    return render_template('project_alternatives.html', project=project, alternatives=alternatives, recommended=recommended, chart_max=chart_max)


@app.route('/project/<project_id>/alternatives.xlsx')
@login_required
def project_alternatives_excel(project_id):
    collection = get_project_store()
    project = collection.find_one({'user_id': session['user_id'], **project_id_query(project_id)}) if hasattr(collection, 'find_one') else None
    if not project:
        return render_template('error.html', code=404, message='Project not found.'), 404

    alternatives = project.get('design_alternatives') or []
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as workbook:
        rows = [
            ['Name', 'Status', 'Built-up area', 'Materials cost', 'Labour cost', 'Other cost', 'Total cost', 'Description'],
        ]
        for alt in alternatives:
            rows.append([
                alt.get('name', ''),
                alt.get('status', ''),
                alt.get('built_up_area', ''),
                alt.get('materials_cost', 0),
                alt.get('labour_cost', 0),
                alt.get('other_cost', 0),
                alt.get('total_cost', 0),
                alt.get('description', ''),
            ])

        content = '"' + '";"'.join(rows[0]) + '"\n'
        for row in rows[1:]:
            escaped = []
            for value in row:
                text = str(value).replace('"', '""')
                escaped.append(text)
            content += '"' + '";"'.join(escaped) + '"\n'

        workbook.writestr('xl/workbook.xml', '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets><sheet name="Alternatives" sheetId="1" r:id="rId1"/></sheets></workbook>')
        workbook.writestr('xl/_rels/workbook.xml.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        workbook.writestr('xl/worksheets/sheet1.xml', '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Name</t></is></c><c r="B1" t="inlineStr"><is><t>Status</t></is></c><c r="C1" t="inlineStr"><is><t>Built-up area</t></is></c><c r="D1" t="inlineStr"><is><t>Materials cost</t></is></c><c r="E1" t="inlineStr"><is><t>Labour cost</t></is></c><c r="F1" t="inlineStr"><is><t>Other cost</t></is></c><c r="G1" t="inlineStr"><is><t>Total cost</t></is></c><c r="H1" t="inlineStr"><is><t>Description</t></is></c></row>' + ''.join([
            f'<row r="{idx + 2}"><c r="A{idx + 2}" t="inlineStr"><is><t>{alt.get("name", "")}</t></is></c><c r="B{idx + 2}" t="inlineStr"><is><t>{alt.get("status", "")}</t></is></c><c r="C{idx + 2}" t="n"><v>{alt.get("built_up_area", 0)}</v></c><c r="D{idx + 2}" t="n"><v>{alt.get("materials_cost", 0)}</v></c><c r="E{idx + 2}" t="n"><v>{alt.get("labour_cost", 0)}</v></c><c r="F{idx + 2}" t="n"><v>{alt.get("other_cost", 0)}</v></c><c r="G{idx + 2}" t="n"><v>{alt.get("total_cost", 0)}</v></c><c r="H{idx + 2}" t="inlineStr"><is><t>{alt.get("description", "")}</t></is></c></row>' for idx, alt in enumerate(alternatives)
        ]) + '</sheetData></worksheet>')
        workbook.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        workbook.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')

    stream.seek(0)
    return send_file(stream, as_attachment=True, download_name=f'{project.get("project_name", "project")}-alternatives.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/project/<project_id>/alternatives/report.pdf')
@login_required
def project_alternatives_report_pdf(project_id):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    collection = get_project_store()
    project = collection.find_one({'user_id': session['user_id'], **project_id_query(project_id)}) if hasattr(collection, 'find_one') else None
    if not project:
        return render_template('error.html', code=404, message='Project not found.'), 404

    alternatives = project.get('design_alternatives') or []
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4)
    y = 800
    pdf.setTitle(f'{project.get("project_name", "Project")} alternative comparison report')
    pdf.setFont('Helvetica-Bold', 18)
    pdf.drawString(50, y, f"Design Alternatives - {project.get('project_name', 'Project')}")
    y -= 30
    pdf.setFont('Helvetica', 11)
    pdf.drawString(50, y, f"Prepared for: {session.get('user_name', '')}")
    y -= 22
    pdf.drawString(50, y, f"Plot: {project.get('plot_length')} x {project.get('plot_width')} {project.get('unit', 'ft')}")
    y -= 22
    pdf.drawString(50, y, f"Floors: {project.get('floors', 0)}")
    y -= 30

    if not alternatives:
        pdf.drawString(50, y, 'No design alternatives have been added yet.')
    else:
        for alt in alternatives:
            if y < 120:
                pdf.showPage(); y = 800
            pdf.setFont('Helvetica-Bold', 12)
            pdf.drawString(50, y, f"{alt.get('name', 'Alternative')} - {alt.get('status', 'concept').title()}")
            y -= 18
            pdf.setFont('Helvetica', 10)
            pdf.drawString(50, y, f"Built-up area: {alt.get('built_up_area', 0)} sq units")
            y -= 16
            pdf.drawString(50, y, f"Materials: ₹{alt.get('materials_cost', 0):,.0f} | Labour: ₹{alt.get('labour_cost', 0):,.0f} | Other: ₹{alt.get('other_cost', 0):,.0f}")
            y -= 16
            pdf.drawString(50, y, f"Total cost: ₹{alt.get('total_cost', 0):,.0f}")
            y -= 18
            if alt.get('description'):
                pdf.drawString(50, y, f"Notes: {alt.get('description', '')[:90]}")
                y -= 18
            y -= 10

    pdf.save(); stream.seek(0)
    return send_file(stream, as_attachment=True, download_name=f'{project.get("project_name", "project")}-comparison-report.pdf', mimetype='application/pdf')


@app.route('/project/<project_id>/versions', methods=['GET'])
@login_required
def project_versions(project_id):
    collection = get_project_store()
    project = collection.find_one({'user_id': session['user_id'], **project_id_query(project_id)}) if hasattr(collection, 'find_one') else None
    
    if not project:
        flash('Project not found.', 'danger')
        return redirect(url_for('projects'))
    
    versions = project.get('versions', [])
    return render_template('project_versions.html', project=project, versions=versions)


@app.route('/support', methods=['GET', 'POST'])
def support():
    agent = VishwakarmaAI()
    conversation_store = SupportConversationStore()
    ticket_store = SupportTicketStore()
    session_id = session.get('support_session_id') or f"session-{uuid.uuid4()}"
    session['support_session_id'] = session_id

    response = None
    question = ''
    history = conversation_store.load(session_id)

    if request.method == 'POST':
        question = request.form.get('question', '').strip()
        if request.form.get('train_question'):
            train_question = request.form.get('train_question', '').strip()
            train_answer = request.form.get('train_answer', '').strip()
            train_category = request.form.get('train_category', 'general').strip()
            if train_question and train_answer:
                response = agent.train(train_question, train_answer, train_category)
                conversation_store.append(session_id, {'role': 'assistant', 'text': f"Training complete: {train_question}"})
                flash('Support knowledge updated successfully.', 'success')
            else:
                flash('Please provide both a question and an answer to train the support agent.', 'warning')
        elif question:
            conversation_store.append(session_id, {'role': 'user', 'text': question})
            response = agent.answer(question, user_id=session.get('user_id'))
            conversation_store.append(session_id, {'role': 'assistant', 'text': response.get('answer', '')})
            ticket_store.log(session_id, {'question': question, 'answer': response.get('answer', ''), 'status': response.get('status', 'unknown')})
            flash('Support agent reviewed your issue.', 'info')
        else:
            flash('Please enter a question for the support agent.', 'warning')

    history = conversation_store.load(session_id)
    return render_template('support.html', response=response, question=question, knowledge=agent.knowledge, chat_history=history)


@app.route('/api/support/ask', methods=['POST'])
def support_api():
    data = request.get_json(silent=True) or {}
    question = (data.get('question') or '').strip()
    agent = VishwakarmaAI()
    return jsonify(agent.answer(question, user_id=session.get('user_id')))


@app.route('/health')
def health():
    try:
        db_available = _mongo_available()
        return jsonify({
            'status': 'ok',
            'service': 'smart-house-planner',
            'storage_mode': 'mongodb' if db_available else 'file',
            'mongodb_available': db_available,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })
    except Exception as exc:
        return jsonify({
            'status': 'error',
            'service': 'smart-house-planner',
            'storage_mode': 'file',
            'mongodb_available': False,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'error': str(exc)
        }), 500


@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', code=404, message='The page you requested could not be found.'), 404


@app.errorhandler(500)
def server_error(error):
    return render_template('error.html', code=500, message='Something went wrong. Please try again.'), 500


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', '5000')),
        debug=os.getenv('FLASK_DEBUG', '0') == '1',
    )
