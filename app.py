import atexit
import base64
import binascii
import io
import json
import math
import os
import random
import re
import smtplib
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
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
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename
from construction_modules import (
    FileResourceRepository,
    MongoResourceRepository,
    RESOURCE_SCHEMAS,
    ResourceValidationError,
    serialize_resource,
    validate_resource,
)
from material_estimation import (
    DRY_VOLUME_FACTOR,
    EstimationError,
    MIX_RATIOS,
    PRICE_LABELS,
    UTTARAKHAND_DISTRICTS,
    calculate_estimate as calculate_advanced_estimate,
    calculate_steel_bars,
    normalize_rate_record,
)
from vastu_engine import (
    DIRECTIONS,
    DIRECTION_LABELS,
    PRIORITY_WEIGHTS,
    STANDARD_RULE_LIBRARY,
    VASTU_COMPONENTS,
    VASTU_RULES,
    analyze_vastu,
    analyze_rule_sets,
    directions_from_layout,
)
from vastu_consultant import answer_vastu_question

import logging

load_dotenv()
logger = logging.getLogger('vishwakarma_ai')
app = Flask(__name__)
SECRET_KEY_CONFIGURED = bool((os.getenv('SECRET_KEY') or '').strip())
app.config['SECRET_KEY'] = (
    (os.getenv('SECRET_KEY') or '').strip()
    or (None if os.getenv('VERCEL') == '1' else 'development-only-change-me')
)
app.config['MONGO_URI'] = (os.getenv('MONGO_URI') or 'mongodb://localhost:27017/smart_house_planner?serverSelectionTimeoutMS=2000').strip() or 'mongodb://localhost:27017/smart_house_planner?serverSelectionTimeoutMS=2000'


class DatabaseUnavailableError(RuntimeError):
    pass


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
MATERIAL_UNITS = {
    'cement': '50 kg bag(s)',
    'sand': 'app units (unit unspecified)',
    'aggregate': 'app units (unit unspecified)',
    'bricks': 'app units (unit unspecified)',
    'steel': 'app units (unit unspecified)',
    'flooring': 'app units (unit unspecified)',
    'paint': 'app units (unit unspecified)',
}
PROJECT_ESTIMATE_PHASES = [
    {
        'key': 'site_foundation',
        'name': 'Site preparation & foundation',
        'items': [
            {'key': 'excavation', 'name': 'Earth excavation', 'unit': 'm³'},
            {'key': 'pcc', 'name': 'PCC / levelling concrete', 'unit': 'm³'},
            {'key': 'foundation_concrete', 'name': 'Foundation concrete (drawing quantity)', 'unit': 'm³'},
            {'key': 'foundation_waterproofing', 'name': 'Foundation waterproofing', 'unit': 'm²'},
            {'key': 'backfilling', 'name': 'Backfilling / compaction', 'unit': 'm³'},
        ],
    },
    {
        'key': 'structure',
        'name': 'RCC structure',
        'items': [
            {'key': 'rcc', 'name': 'RCC concrete (approved drawings)', 'unit': 'm³'},
            {'key': 'reinforcement', 'name': 'Reinforcement steel (BBS quantity)', 'unit': 'kg'},
            {'key': 'formwork', 'name': 'Formwork / shuttering contact area', 'unit': 'm²'},
            {'key': 'structural_labour', 'name': 'Structural labour', 'unit': 'item'},
        ],
    },
    {
        'key': 'masonry',
        'name': 'Masonry & openings',
        'items': [
            {'key': 'exterior_masonry', 'name': 'Exterior wall masonry', 'unit': 'm³'},
            {'key': 'interior_masonry', 'name': 'Interior partition masonry', 'unit': 'm³'},
            {'key': 'doors_windows', 'name': 'Doors & windows supply / fitting', 'unit': 'item'},
            {'key': 'grills_railings', 'name': 'Grills, railings & metalwork', 'unit': 'm'},
        ],
    },
    {
        'key': 'interior',
        'name': 'Interior finishing',
        'items': [
            {'key': 'interior_plaster', 'name': 'Internal wall plaster', 'unit': 'm²'},
            {'key': 'ceiling_plaster', 'name': 'Ceiling plaster / finish', 'unit': 'm²'},
            {'key': 'interior_flooring', 'name': 'Interior flooring / tiles', 'unit': 'm²'},
            {'key': 'skirting', 'name': 'Floor skirting', 'unit': 'm'},
            {'key': 'interior_paint', 'name': 'Interior paint / putty', 'unit': 'm²'},
            {'key': 'false_ceiling', 'name': 'False ceiling', 'unit': 'm²'},
            {'key': 'interior_waterproofing', 'name': 'Bathroom / wet-area waterproofing', 'unit': 'm²'},
            {'key': 'kitchen_cabinets', 'name': 'Kitchen cabinets / wardrobes', 'unit': 'item'},
        ],
    },
    {
        'key': 'exterior',
        'name': 'Exterior finishing & site works',
        'items': [
            {'key': 'exterior_plaster', 'name': 'External wall plaster', 'unit': 'm²'},
            {'key': 'exterior_paint', 'name': 'Exterior paint / texture', 'unit': 'm²'},
            {'key': 'roof_waterproofing', 'name': 'Terrace / roof waterproofing', 'unit': 'm²'},
            {'key': 'paving', 'name': 'External paving / driveway', 'unit': 'm²'},
            {'key': 'boundary_wall', 'name': 'Boundary wall', 'unit': 'm³'},
            {'key': 'drainage', 'name': 'External drainage / rainwater pipes', 'unit': 'm'},
            {'key': 'landscaping', 'name': 'Landscaping / other exterior works', 'unit': 'item'},
        ],
    },
    {
        'key': 'services',
        'name': 'Electrical, plumbing & services',
        'items': [
            {'key': 'electrical_points', 'name': 'Electrical points (as per plan)', 'unit': 'points'},
            {'key': 'wiring', 'name': 'Electrical wire / conduit', 'unit': 'm'},
            {'key': 'plumbing_fixtures', 'name': 'Plumbing fixtures', 'unit': 'points'},
            {'key': 'water_pipes', 'name': 'Water supply / waste pipes', 'unit': 'm'},
            {'key': 'service_labour', 'name': 'Services labour / commissioning', 'unit': 'item'},
        ],
    },
]

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
        'account': 'Register and log in with an email and password; no account verification code is required. File JSON stores are used when MongoDB is unavailable.',
        'dashboard': 'Shows recent saved projects, built-up area, indicative cost, solar output, and rainwater potential.',
        'planner': 'Planner accepts plot length, plot width, unit, floors, room counts, and room dimensions. It computes plot area, 70% preliminary coverage, built-up area, and open area, and can save a project.',
        'visualization': 'Planner includes a 2D layout workflow and a 3D View control with front, side, top, floor selection, and building style controls.',
        'materials': 'The Materials page now includes a measured brickwork calculator for brick count and mortar cement/sand, plus a concrete geometric-volume calculator from entered member dimensions. Brick dimensions, mortar ratio, dry-volume factor, and wastage are inputs/assumptions; verify them against project specifications. The concrete tool does not infer concrete mix, steel, strength, or safety. A separate legacy area estimate remains a rough planning assumption: cement 0.45 50 kg bags per sq ft per floor, while other material units are unspecified.',
        'cost': 'The /cost page has a simple estimate: total built-up area (area per floor × floors) multiplied by a local rate supplied by the user. It also has optional detailed category costing with a 5% contingency. What-if construction cost is a separate educational formula.',
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
    'materials': 'Open Materials for dimension-based estimates. For brickwork, enter wall dimensions, openings, brick size, and the specified mortar ratio; the app estimates brick pieces, mortar cement in 50 kg bags, and sand volume. The concrete calculator uses entered slab/column/beam/footing dimensions to calculate geometric volume only. It does not choose concrete mix, estimate steel, predict strength, or check safety. Verify all dimensions and mix specifications with project drawings and a qualified professional. The separate legacy area formula is rough planning only, not an IS-code quantity takeoff.',
    'cost': 'For a quick rough estimate, open /cost and enter the built-up area per floor, number of floors, and a local per-sq-ft rate quoted by a mason or contractor. The app multiplies these values; confirm what the local rate includes. Detailed category costing is optional below the simple calculator and adds a 5% reserve. The What-if simulator is separate.',
    'solar': 'Solar uses monthly electricity usage, panel wattage, and sunlight hours. The current formula estimates capacity as monthly usage ÷ (30 × sunlight hours × 0.8), then rounds up the panel count.',
    'rainwater': 'Rainwater uses roof area × annual rainfall × runoff coefficient for litres per year and divides by 12 for monthly potential. Use local rainfall and roof data for a better estimate.',
    'simulation': 'Simulation Lab contains Material, Load, Solar, Rainwater, Cost, What-if, and 3D visualization modules. It is for educational and preliminary planning only, not professional certification.',
    'projects': 'Use Save Project in Planner to create a saved project. Saved projects can be opened and edited, reported as PDF, shared, commented on, assigned team members, and reviewed through version history.',
    'reports': 'Open a saved project and choose Report. The report page provides the project summary and the PDF report route for download.',
    'account': 'Use Register to create an account and Log in to access the dashboard and saved project features. No verification code is required.',
}


def _has_openai_config():
    return bool(os.getenv('OPENAI_API_KEY'))


def _has_azure_config():
    return bool(os.getenv('AZURE_OPENAI_API_KEY') and os.getenv('AZURE_OPENAI_ENDPOINT') and os.getenv('AZURE_OPENAI_DEPLOYMENT'))


def _env_bool(name, default=False):
    return str(os.getenv(name, default)).strip().lower() in {'1', 'true', 'yes', 'on'}


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
    project_area_used = area is None
    if area is None:
        area = _ai_number(project_context.get('built_up_area'))
    context = {}
    local_answer = None
    intent = _ai_intent(question)

    if intent == 'materials' and area:
        result = calculate_materials(area, 1 if project_area_used else floors)
        area_basis = 'saved total built-up area' if project_area_used else 'entered area per floor'
        other_materials = ', '.join(
            f"{name} {result[name]:g}" for name in result if name != 'cement'
        )
        context['calculator_result'] = {
            'calculator': 'calculate_materials',
            'inputs': {'area': area, 'area_basis': area_basis, 'floors': floors},
            'outputs': result,
            'basis': (
                'Cement: 0.45 50 kg bags per sq ft per floor, rounded up to whole bags; '
                'a rough planning assumption, not IS-code takeoff. Other legacy factors '
                'have unspecified physical units.'
            ),
        }
        area_description = (
            f"{area:g} sq ft total built-up area from saved project"
            if project_area_used
            else f"{area:g} sq ft per floor for {floors} floor(s)"
        )
        local_answer = (
            f"For {area_description}, the rough cement estimate is about {result['cement']:g} "
            f"50 kg bags, using 0.45 bags per sq ft per floor and rounding up to whole bags. "
            f"Other legacy app quantities are: {other_materials}; their physical units are not "
            "defined. This is not an IS-code bill of quantities or verified purchase list. "
            "The app does not calculate concrete strength."
        )
    elif intent == 'cost' and area:
        result = _simulation_what_if({'built_up_area': area, 'floors': floors})
        context['calculator_result'] = {'calculator': '_simulation_what_if', 'inputs': {'built_up_area': area, 'floors': floors}, 'outputs': {'estimated_construction_cost': result['estimated_construction_cost']}}
        local_answer = f"For {area:g} sq ft and {floors} floor(s), the app's preliminary what-if construction estimate is ₹{result['estimated_construction_cost']:,.0f}. It uses built-up area × 140 + floors × 2,500. For a local-rate estimate, enter your area's contractor quote on /cost; that estimate uses total area × the rate you provide."
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
        normalized_email = self._normalize_email(email)
        if not normalized_email:
            return None
        record = users.get(normalized_email)
        if isinstance(record, dict):
            return record
        for key, candidate in users.items():
            if not isinstance(candidate, dict):
                continue
            candidate_email = candidate.get('email') or key
            if self._normalize_email(candidate_email) == normalized_email:
                return candidate
        return None

    def verify_password(self, email, password):
        user = self.find_by_email(email)
        password_hash = user.get('password_hash') if isinstance(user, dict) else None
        if password_hash:
            try:
                if check_password_hash(password_hash, password):
                    return user
            except (TypeError, ValueError):
                return None
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


def _mongo_uri_configured():
    value = (os.getenv('MONGO_URI') or '').strip()
    if not value:
        return False
    lowered = value.lower()
    return not any(marker in lowered for marker in ('replace_with_', 'your-', 'example', '******'))


def _mongo_available():
    try:
        if mongo is None or not hasattr(mongo, 'cx'):
            return False
        mongo.cx.admin.command('ping')
        return True
    except Exception as exc:
        logger.warning('MongoDB ping failed (%s).', type(exc).__name__)
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
        record = self.collection.find_one({'email': normalized_email})
        if record:
            return record
        return self.collection.find_one({
            'email': {
                '$regex': '^{}$'.format(re.escape(normalized_email)),
                '$options': 'i',
            }
        })

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
        password_hash = user.get('password_hash') if isinstance(user, dict) else None
        if password_hash:
            try:
                if check_password_hash(password_hash, password):
                    return user
            except (TypeError, ValueError):
                return None
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
            return code if delivered else None
        if channel in {'mobile', 'whatsapp'}:
            phone_number = self._normalize_phone(user.get('phone'))
            if phone_number:
                delivered = send_sms_message(phone_number, f'Your Smart House Planner verification code is {code}. It expires in 15 minutes.', channel='whatsapp' if channel == 'whatsapp' else 'sms')
            return code if delivered else None
        return None

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
        users = db_collection('users')
        if users is not None:
            return MongoUserStore(users)
    if os.getenv('VERCEL') == '1':
        raise DatabaseUnavailableError('MongoDB is unavailable. Check the MONGO_URI environment variable in Vercel.')
    return FileUserStore(USER_STORE_PATH)


def get_project_store():
    if _mongo_available():
        projects = db_collection('projects')
        if projects is not None:
            return projects
    if os.getenv('VERCEL') == '1':
        raise DatabaseUnavailableError('MongoDB is unavailable. Check the MONGO_URI environment variable in Vercel.')
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
    if os.getenv('VERCEL') == '1':
        raise DatabaseUnavailableError('MongoDB is unavailable. Check the MONGO_URI environment variable in Vercel.')
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


def _validate_vastu_rule_payload(payload, user_id):
    if not isinstance(payload, dict):
        raise ResourceValidationError('Rule data must be an object.')

    rule_name = str(payload.get('rule_name') or '').strip()
    component = str(payload.get('component') or '').strip()
    preferred = str(payload.get('preferred_direction') or '').strip().upper()
    description = str(payload.get('description') or '').strip()
    recommendation = str(payload.get('recommendation') or '').strip()
    priority = str(payload.get('priority') or 'medium').strip().lower()
    alternatives = payload.get('alternative_directions', [])

    if not rule_name or len(rule_name) > 100:
        raise ResourceValidationError('Rule name is required and must be 100 characters or fewer.')
    if component not in VASTU_COMPONENTS:
        raise ResourceValidationError('Choose a valid building component.')
    if preferred not in DIRECTIONS:
        raise ResourceValidationError('Choose a valid preferred direction.')
    if not isinstance(alternatives, list) or any(
        not isinstance(direction, str) or direction.upper() not in DIRECTIONS
        for direction in alternatives
    ):
        raise ResourceValidationError('Alternative directions must be a list of valid directions.')
    alternatives = list(dict.fromkeys(direction.upper() for direction in alternatives if direction.upper() != preferred))
    if priority not in PRIORITY_WEIGHTS:
        raise ResourceValidationError('Priority must be Low, Medium, or High.')
    if len(description) > 1000 or len(recommendation) > 1000:
        raise ResourceValidationError('Description and recommendation must be 1,000 characters or fewer.')
    if 'enabled' in payload and not isinstance(payload['enabled'], bool):
        raise ResourceValidationError('Enabled must be true or false.')

    return {
        'user_id': str(user_id),
        'resource_type': 'vastu_rules',
        'rule_name': rule_name,
        'component': component,
        'preferred_direction': preferred,
        'preferred_directions': [preferred],
        'preferred_labels': [DIRECTION_LABELS[preferred]],
        'alternative_directions': alternatives,
        'alternative_labels': [DIRECTION_LABELS[direction] for direction in alternatives],
        'description': description,
        'priority': priority,
        'recommendation': recommendation,
        'source': 'User-defined custom rule',
        'source_status': 'user_defined',
        'category': 'Custom',
        'applicable_conditions': 'User-defined; confirm suitability for this plan.',
        'enabled': payload.get('enabled', True),
        'weight': PRIORITY_WEIGHTS[priority],
    }


VASTU_ADMIN_OWNER = 'vishwakarma-official'


def _validate_admin_vastu_rule_payload(payload):
    rule = _validate_vastu_rule_payload(payload, VASTU_ADMIN_OWNER)
    source = str(payload.get('source') or '').strip()
    conditions = str(payload.get('applicable_conditions') or '').strip()
    relocation_alternative = str(payload.get('alternative_if_relocation_not_possible') or '').strip()
    if len(source) > 200:
        raise ResourceValidationError('Source must be 200 characters or fewer.')
    if len(conditions) > 1000 or len(relocation_alternative) > 1000:
        raise ResourceValidationError('Conditions and alternatives must be 1,000 characters or fewer.')
    rule.update({
        'resource_type': 'vastu_admin_rules',
        'source': source or 'Admin-configured traditional preference; source not independently verified.',
        'source_status': 'unverified',
        'category': 'Admin configured',
        'applicable_conditions': conditions,
        'alternative_if_relocation_not_possible': relocation_alternative,
    })
    return rule


def _default_admin_vastu_rule(component, rule):
    return {
        'user_id': VASTU_ADMIN_OWNER,
        'resource_type': 'vastu_admin_rules',
        'rule_name': rule['rule_name'],
        'component': component,
        'preferred_direction': rule['preferred'],
        'preferred_directions': [rule['preferred']],
        'preferred_labels': [DIRECTION_LABELS[rule['preferred']]],
        'alternative_directions': list(rule['alternatives']),
        'alternative_labels': [DIRECTION_LABELS[item] for item in rule['alternatives']],
        'description': rule.get('description', ''),
        'priority': rule.get('priority', 'medium'),
        'recommendation': rule.get('recommendation', ''),
        'source': rule.get('source', 'Unverified traditional preference.'),
        'source_status': 'unverified',
        'category': rule.get('category', 'Traditional reference'),
        'applicable_conditions': rule.get('applicable_conditions', ''),
        'alternative_if_relocation_not_possible': (
            'If moving the room is not practical, prioritize ventilation, sanitation, '
            'accessibility, structural safety, and local building requirements.'
        ),
        'enabled': True,
        'weight': rule.get('weight', PRIORITY_WEIGHTS['medium']),
    }


def _admin_vastu_rule_records(repository):
    return repository.list(VASTU_ADMIN_OWNER, resource_type='vastu_admin_rules')


def _ensure_admin_vastu_rules(repository):
    state = repository.list(VASTU_ADMIN_OWNER, resource_type='vastu_admin_rule_state')
    rules = _admin_vastu_rule_records(repository)
    if not state:
        if not rules:
            for component, rule in STANDARD_RULE_LIBRARY.items():
                repository.create(_default_admin_vastu_rule(component, rule))
        repository.create({
            'user_id': VASTU_ADMIN_OWNER,
            'resource_type': 'vastu_admin_rule_state',
            'initialized': True,
        })
    return _admin_vastu_rule_records(repository)


def _configured_admin_vastu_rules(repository):
    rules = _admin_vastu_rule_records(repository)
    state = repository.list(VASTU_ADMIN_OWNER, resource_type='vastu_admin_rule_state')
    if not state and not rules:
        return list(STANDARD_RULE_LIBRARY.values())
    return rules


@app.route('/admin/vastu-rules')
@admin_required
def admin_vastu_rules():
    try:
        repository = get_resource_repository('vastu_admin_rules')
        rules = [serialize_resource(item) for item in _ensure_admin_vastu_rules(repository)]
        return render_template(
            'admin_vastu_rules.html',
            rules=rules,
            component_options=VASTU_COMPONENTS,
            directions=DIRECTIONS,
            direction_labels=DIRECTION_LABELS,
        )
    except (DatabaseUnavailableError, PyMongoError):
        logger.exception('Unable to load admin Vastu rules.')
        return render_template(
            'error.html',
            code=503,
            message='Vastu rule storage is unavailable. Try again after checking the database.',
        ), 503


@app.route('/api/admin/vastu/rules', methods=['GET', 'POST'])
@admin_required
def admin_vastu_rules_api():
    try:
        repository = get_resource_repository('vastu_admin_rules')
        if request.method == 'GET':
            items = [serialize_resource(item) for item in _ensure_admin_vastu_rules(repository)]
            return jsonify({'items': items, 'count': len(items)})
        _ensure_admin_vastu_rules(repository)
        payload = request.get_json(silent=True) or {}
        rule = _validate_admin_vastu_rule_payload(payload)
        item = repository.create(rule)
        return jsonify({'item': serialize_resource(item)}), 201
    except ResourceValidationError as exc:
        return jsonify({'error': str(exc)}), 400
    except (DatabaseUnavailableError, PyMongoError):
        logger.exception('Unable to create admin Vastu rule.')
        return jsonify({'error': 'Vastu rule storage is unavailable.'}), 503


@app.route('/api/admin/vastu/rules/<rule_id>', methods=['GET', 'PATCH', 'DELETE'])
@admin_required
def admin_vastu_rule_item_api(rule_id):
    try:
        repository = get_resource_repository('vastu_admin_rules')
        item = repository.get(VASTU_ADMIN_OWNER, rule_id, 'vastu_admin_rules')
        if not item:
            return jsonify({'error': 'Vastu rule not found.'}), 404
        if request.method == 'GET':
            return jsonify({'item': serialize_resource(item)})
        if request.method == 'DELETE':
            repository.delete(VASTU_ADMIN_OWNER, rule_id, 'vastu_admin_rules')
            return '', 204
        current = serialize_resource(item) or {}
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({'error': 'Rule update must be a JSON object.'}), 400
        current.update(payload)
        rule = _validate_admin_vastu_rule_payload(current)
        updated = repository.update(VASTU_ADMIN_OWNER, rule_id, rule, 'vastu_admin_rules')
        if not updated:
            return jsonify({'error': 'Vastu rule could not be updated.'}), 404
        return jsonify({'item': serialize_resource(updated)})
    except ResourceValidationError as exc:
        return jsonify({'error': str(exc)}), 400
    except (DatabaseUnavailableError, PyMongoError):
        logger.exception('Unable to update admin Vastu rule.')
        return jsonify({'error': 'Vastu rule storage is unavailable.'}), 503


@app.route('/api/vastu/rules', methods=['GET', 'POST'])
@login_required
def vastu_rules_api():
    repository = get_resource_repository('vastu_rules')
    user_id = str(session['user_id'])
    try:
        if request.method == 'GET':
            items = repository.list(user_id, resource_type='vastu_rules')
            return jsonify({'items': [serialize_resource(item) for item in items], 'count': len(items)})
        payload = request.get_json(silent=True) or {}
        rule = _validate_vastu_rule_payload(payload, user_id)
        item = repository.create(rule)
        return jsonify({'item': serialize_resource(item)}), 201
    except ResourceValidationError as exc:
        return jsonify({'error': str(exc)}), 400
    except PyMongoError:
        return jsonify({'error': 'Database is unavailable.'}), 503


@app.route('/api/vastu/rules/<rule_id>', methods=['GET', 'PATCH', 'DELETE'])
@login_required
def vastu_rule_item_api(rule_id):
    repository = get_resource_repository('vastu_rules')
    user_id = str(session['user_id'])
    try:
        item = repository.get(user_id, rule_id, 'vastu_rules')
        if not item:
            return jsonify({'error': 'Custom rule not found.'}), 404
        if request.method == 'GET':
            return jsonify({'item': serialize_resource(item)})
        if request.method == 'DELETE':
            repository.delete(user_id, rule_id, 'vastu_rules')
            return '', 204
        payload = request.get_json(silent=True) or {}
        current = serialize_resource(item) or {}
        current.update(payload)
        rule = _validate_vastu_rule_payload(current, user_id)
        updated = repository.update(user_id, rule_id, rule, 'vastu_rules')
        return jsonify({'item': serialize_resource(updated)})
    except ResourceValidationError as exc:
        return jsonify({'error': str(exc)}), 400
    except PyMongoError:
        return jsonify({'error': 'Database is unavailable.'}), 503


@app.route('/api/vastu/reports', methods=['GET', 'POST'])
@login_required
def vastu_reports_api():
    repository = get_resource_repository('vastu_reports')
    user_id = str(session['user_id'])
    try:
        if request.method == 'GET':
            items = repository.list(user_id, resource_type='vastu_reports')
            return jsonify({'items': [serialize_resource(item) for item in items], 'count': len(items)})
        payload = request.get_json(silent=True) or {}
        project_id = str(payload.get('project_id') or '').strip()
        if not project_id:
            return jsonify({'error': 'Select an analyzed project before saving a report.'}), 400
        project = get_project_store().find_one({
            'user_id': session['user_id'],
            **project_id_query(project_id),
        })
        analysis = project.get('vastu_analysis') if project else None
        if not analysis:
            return jsonify({'error': 'No saved Vastu analysis exists for this project.'}), 404
        report = repository.create({
            'user_id': user_id,
            'resource_type': 'vastu_reports',
            'project_id': project_id,
            'project_name': str(project.get('project_name') or 'Vastu Analysis')[:120],
            'report_name': str(payload.get('report_name') or project.get('project_name') or 'Vastu Analysis')[:120],
            'plot_length': analysis.get('plot_length'),
            'plot_width': analysis.get('plot_width'),
            'unit': project.get('unit', 'ft'),
            'analysis': {
                **analysis,
                'settings': project.get('vastu_settings', {}),
            },
        })
        return jsonify({'item': serialize_resource(report)}), 201
    except PyMongoError:
        return jsonify({'error': 'Database is unavailable.'}), 503


@app.route('/api/vastu/reports/<report_id>', methods=['DELETE'])
@login_required
def vastu_report_item_api(report_id):
    repository = get_resource_repository('vastu_reports')
    user_id = str(session['user_id'])
    try:
        if not repository.get(user_id, report_id, 'vastu_reports'):
            return jsonify({'error': 'Saved report not found.'}), 404
        repository.delete(user_id, report_id, 'vastu_reports')
        return '', 204
    except PyMongoError:
        return jsonify({'error': 'Database is unavailable.'}), 503


MAX_VASTU_IMAGE_BYTES = 8 * 1024 * 1024
MAX_VASTU_CHAT_REQUEST_BYTES = MAX_VASTU_IMAGE_BYTES + 128 * 1024


def _read_vastu_floor_plan(upload):
    if not upload or not upload.filename:
        raise ResourceValidationError('Choose a floor-plan image to upload.')
    content = upload.stream.read(MAX_VASTU_IMAGE_BYTES + 1)
    if len(content) > MAX_VASTU_IMAGE_BYTES:
        raise ResourceValidationError('Floor-plan images must be 8 MB or smaller.')
    detected_type = None
    if content.startswith(b'\x89PNG\r\n\x1a\n'):
        detected_type = 'image/png'
    elif content.startswith(b'\xff\xd8\xff'):
        detected_type = 'image/jpeg'
    elif len(content) >= 12 and content[:4] == b'RIFF' and content[8:12] == b'WEBP':
        detected_type = 'image/webp'
    if detected_type is None or upload.mimetype != detected_type:
        raise ResourceValidationError('Use a valid PNG, JPEG, or WEBP floor-plan image.')
    filename = secure_filename(str(upload.filename).replace('\\', '/').rsplit('/', 1)[-1])[:120] or 'floor-plan'
    return content, detected_type, filename


def _vastu_vision_answer(question, image_data, image_type, project, rules, analysis):
    if not _has_openai_config():
        raise RuntimeError('Floor-plan AI is not configured. Set OPENAI_API_KEY on the server.')

    active_rules = [
        {
            'room': rule.get('rule_name') or rule.get('component'),
            'preferred_directions': rule.get('preferred_directions') or [rule.get('preferred_direction')],
            'alternatives': rule.get('alternative_directions') or [],
            'recommendation': rule.get('recommendation') or '',
        }
        for rule in (rules or [])
        if isinstance(rule, dict) and rule.get('enabled', True)
    ][:30]
    analysis_rules = (analysis or {}).get('analysis_details', {}).get('rules', [])
    known_directions = {
        rule.get('component_label') or rule.get('component'): rule.get('actual_direction_label')
        for rule in analysis_rules
        if isinstance(rule, dict) and rule.get('actual_direction') in DIRECTIONS
    }
    project_context = {
        'project_name': (project or {}).get('project_name', ''),
        'plot_length': (project or {}).get('plot_length'),
        'plot_width': (project or {}).get('plot_width'),
        'unit': (project or {}).get('unit', 'ft'),
        'north_direction': ((project or {}).get('vastu_settings') or {}).get('north_direction'),
        'known_room_directions': known_directions,
        'active_traditional_rules': active_rules,
    }
    instructions = (
        'You are a cautious Vastu floor-plan assistant. Read visible room labels and describe only what is '
        'reasonably visible. Do not guess room positions, compass orientation, or North when they are unclear; '
        'state uncertainty and ask the user to confirm. Use the supplied active rules only as traditional '
        'cultural preferences, never as scientific facts or guaranteed outcomes. Do not assess structural '
        'safety, building-code compliance, or engineering. Do not tell users to move structural walls. '
        'Give practical, non-structural suggestions and recommend a qualified professional for design or '
        "safety decisions. Match the language of the user's question (Hindi, Roman Hindi, or English)."
    )
    prompt = (
        f"User question: {question}\n"
        f"Verified app context (may be incomplete): {json.dumps(project_context, ensure_ascii=False)}\n"
        'If the image has no clear North marker, explain that compass directions cannot be confirmed from '
        'the drawing alone.'
    )
    image_url = f"data:{image_type};base64,{base64.b64encode(image_data).decode('ascii')}"
    messages = [
        {'role': 'system', 'content': instructions},
        {
            'role': 'user',
            'content': [
                {'type': 'text', 'text': prompt},
                {'type': 'image_url', 'image_url': {'url': image_url, 'detail': 'high'}},
            ],
        },
    ]
    answer = _call_llm(messages)
    if not answer:
        raise RuntimeError('OpenAI did not return a floor-plan analysis.')
    return answer


def _cleanup_vastu_resource(repository, user_id, resource_id, resource_type):
    if not repository or not resource_id:
        return
    try:
        if not repository.delete(user_id, resource_id, resource_type):
            logger.warning('Could not remove a partially saved Vastu resource (%s).', resource_type)
    except (DatabaseUnavailableError, PyMongoError, OSError):
        logger.exception('Could not clean up a partially saved Vastu resource (%s).', resource_type)


@app.route('/api/vastu/consultations', methods=['GET'])
@login_required
def vastu_consultations_api():
    try:
        repository = get_resource_repository('vastu_consultations')
        items = repository.list(session['user_id'], resource_type='vastu_consultations')
        items.sort(key=lambda item: str(item.get('updated_at') or item.get('created_at') or ''), reverse=True)
        summaries = []
        for item in items[:30]:
            messages = item.get('messages') or []
            last_message = next(
                (message.get('content', '') for message in reversed(messages) if message.get('role') == 'assistant'),
                '',
            )
            summaries.append({
                'id': str(item.get('_id') or item.get('id') or ''),
                'title': item.get('title') or 'Vastu consultation',
                'created_at': item.get('created_at'),
                'updated_at': item.get('updated_at') or item.get('created_at'),
                'last_message': last_message[:180],
            })
        return jsonify({'items': summaries, 'count': len(summaries)})
    except (DatabaseUnavailableError, PyMongoError):
        logger.exception('Unable to load Vastu consultation history.')
        return jsonify({'error': 'Consultation history is unavailable.'}), 503


@app.route('/api/vastu/consultations/<consultation_id>', methods=['GET'])
@login_required
def vastu_consultation_api(consultation_id):
    try:
        repository = get_resource_repository('vastu_consultations')
        item = repository.get(session['user_id'], consultation_id, 'vastu_consultations')
        if not item:
            return jsonify({'error': 'Consultation not found.'}), 404
        return jsonify({'item': serialize_resource(item)})
    except (DatabaseUnavailableError, PyMongoError):
        logger.exception('Unable to load Vastu consultation.')
        return jsonify({'error': 'Consultation history is unavailable.'}), 503


@app.route('/api/vastu/consultations/<consultation_id>/images/<image_id>')
@login_required
def vastu_consultation_image_api(consultation_id, image_id):
    user_id = session['user_id']
    try:
        consultations = get_resource_repository('vastu_consultations')
        consultation = consultations.get(user_id, consultation_id, 'vastu_consultations')
        if not consultation:
            return jsonify({'error': 'Consultation not found.'}), 404
        is_attached = any(
            attachment.get('id') == image_id
            for message in consultation.get('messages', [])
            if isinstance(message, dict)
            for attachment in message.get('attachments', [])
            if isinstance(attachment, dict)
        )
        if not is_attached:
            return jsonify({'error': 'Image not found.'}), 404
        images = get_resource_repository('vastu_consultation_images')
        image = images.get(user_id, image_id, 'vastu_consultation_images')
        if not image or str(image.get('consultation_id')) != str(consultation_id):
            return jsonify({'error': 'Image not found.'}), 404
        try:
            image_data = base64.b64decode(image.get('image_data') or '', validate=True)
        except (ValueError, binascii.Error):
            logger.error('Stored Vastu image %s is not valid base64.', image_id)
            return jsonify({'error': 'Stored floor-plan image is unavailable.'}), 500
        response = send_file(
            io.BytesIO(image_data),
            mimetype=image.get('mime_type', 'application/octet-stream'),
            download_name=image.get('filename') or 'floor-plan',
            conditional=False,
        )
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    except (DatabaseUnavailableError, PyMongoError, OSError):
        logger.exception('Unable to load a saved Vastu floor-plan image.')
        return jsonify({'error': 'Floor-plan image storage is unavailable.'}), 503


@app.route('/api/vastu/chat', methods=['POST'])
@login_required
def vastu_chat_api():
    request.max_content_length = MAX_VASTU_CHAT_REQUEST_BYTES
    if request.content_length is not None and request.content_length > MAX_VASTU_CHAT_REQUEST_BYTES:
        return jsonify({'error': 'Floor-plan uploads must be 8 MB or smaller.'}), 413
    image_file = None
    if request.mimetype == 'multipart/form-data':
        try:
            payload = request.form.to_dict()
            image_file = request.files.get('floor_plan')
        except RequestEntityTooLarge:
            return jsonify({'error': 'Floor-plan uploads must be 8 MB or smaller.'}), 413
    else:
        payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'Send a JSON object with a question.'}), 400
    question = payload.get('question')
    if not isinstance(question, str) or not question.strip() or len(question.strip()) > 500:
        return jsonify({'error': 'Question is required and must be 500 characters or fewer.'}), 400
    question = question.strip()
    image_data = None
    image_type = None
    image_filename = None
    if image_file:
        if payload.get('openai_consent') != 'true':
            return jsonify({'error': 'Confirm that this image, question, and relevant project context may be sent to OpenAI.'}), 400
        try:
            image_data, image_type, image_filename = _read_vastu_floor_plan(image_file)
        except ResourceValidationError as exc:
            return jsonify({'error': str(exc)}), 400
        if not _has_openai_config():
            return jsonify({'error': 'Floor-plan AI is not configured. Set OPENAI_API_KEY on the server.'}), 503

    user_id = session['user_id']
    consultation_id = str(payload.get('consultation_id') or '').strip()
    project_id = str(payload.get('project_id') or '').strip()
    try:
        repository = get_resource_repository('vastu_consultations')
        if consultation_id:
            consultation = repository.get(user_id, consultation_id, 'vastu_consultations')
            if not consultation:
                return jsonify({'error': 'Consultation not found.'}), 404
            consultation = serialize_resource(consultation)
            project_id = str(consultation.get('project_id') or '')
        else:
            consultation = None

        project = None
        if project_id:
            projects_store = get_project_store()
            project = projects_store.find_one({
                'user_id': user_id,
                **project_id_query(project_id),
            }) if hasattr(projects_store, 'find_one') else None
            if not project:
                return jsonify({'error': 'Selected project was not found.'}), 404

        global_rules = _configured_admin_vastu_rules(get_resource_repository('vastu_admin_rules'))
        rules = list(global_rules)
        analysis = (project or {}).get('vastu_analysis') or {}
        if analysis.get('analysis_mode') in {'custom', 'combined'}:
            personal_repository = get_resource_repository('vastu_rules')
            rules.extend(personal_repository.list(user_id, resource_type='vastu_rules'))
        if image_data:
            try:
                answer = _vastu_vision_answer(
                    question,
                    image_data,
                    image_type,
                    project,
                    rules,
                    analysis,
                )
            except HTTPError as exc:
                logger.warning('OpenAI Vastu vision request failed with HTTP %s.', exc.code)
                if exc.code in {401, 403}:
                    message = 'OpenAI rejected its server credentials or model access. Check OPENAI_API_KEY and OPENAI_MODEL.'
                elif exc.code == 429:
                    message = 'OpenAI is rate-limiting requests. Wait a little and try again.'
                else:
                    message = 'OpenAI could not analyze this floor plan. Try again later.'
                return jsonify({'error': message}), 502
            except (URLError, TimeoutError):
                logger.exception('OpenAI Vastu vision service is unreachable.')
                return jsonify({'error': 'OpenAI is temporarily unreachable. Try again later.'}), 503
            except (json.JSONDecodeError, RuntimeError) as exc:
                logger.exception('OpenAI Vastu vision returned an unusable response: %s', exc)
                return jsonify({'error': str(exc) or 'OpenAI returned an unusable response.'}), 502
        else:
            answer = answer_vastu_question(question, rules, project, analysis)
        timestamp = datetime.now(timezone.utc).isoformat()
        messages = list((consultation or {}).get('messages') or [])
        user_message = {'role': 'user', 'content': question, 'created_at': timestamp}
        image_repository = None
        image_record = None
        attachment = None
        if image_data:
            image_repository = get_resource_repository('vastu_consultation_images')
            image_record = image_repository.create({
                'user_id': user_id,
                'resource_type': 'vastu_consultation_images',
                'consultation_id': consultation_id,
                'filename': image_filename,
                'mime_type': image_type,
                'image_data': base64.b64encode(image_data).decode('ascii'),
            })
            attachment = {
                'id': str(image_record.get('_id') or image_record.get('id') or ''),
                'filename': image_filename,
                'mime_type': image_type,
            }
            user_message['attachments'] = [attachment]
        messages.extend([
            user_message,
            {'role': 'assistant', 'content': answer, 'created_at': timestamp},
        ])
        title = (consultation or {}).get('title') or question[:80]
        document = {
            'user_id': user_id,
            'resource_type': 'vastu_consultations',
            'title': title,
            'project_id': str((project or {}).get('_id') or (project or {}).get('id') or ''),
            'messages': messages,
            'updated_at': timestamp,
        }
        created_consultation = None
        if consultation:
            item = repository.update(user_id, consultation_id, document, 'vastu_consultations')
            if not item:
                if image_record:
                    _cleanup_vastu_resource(
                        image_repository,
                        user_id,
                        attachment['id'],
                        'vastu_consultation_images',
                    )
                return jsonify({'error': 'Consultation could not be saved.'}), 503
        else:
            item = repository.create(document)
            created_consultation = item
        serialized = serialize_resource(item)
        saved_consultation_id = str(serialized.get('id') or '')
        if image_record and not consultation:
            linked_image = image_repository.update(
                user_id,
                attachment['id'],
                {'consultation_id': saved_consultation_id},
                'vastu_consultation_images',
            )
            if not linked_image:
                _cleanup_vastu_resource(
                    image_repository,
                    user_id,
                    attachment['id'],
                    'vastu_consultation_images',
                )
                if created_consultation:
                    _cleanup_vastu_resource(
                        repository,
                        user_id,
                        saved_consultation_id,
                        'vastu_consultations',
                    )
                logger.error('Could not link uploaded Vastu image to its consultation.')
                return jsonify({'error': 'Floor-plan image could not be attached to the saved consultation.'}), 503
        return jsonify({
            'consultation_id': saved_consultation_id,
            'answer': answer,
            'messages': messages,
            'title': title,
            'attachment': attachment,
        })
    except (DatabaseUnavailableError, PyMongoError, OSError):
        logger.exception('Unable to save Vastu consultation.')
        if 'image_record' in locals() and image_record and image_repository:
            _cleanup_vastu_resource(
                image_repository,
                user_id,
                attachment['id'],
                'vastu_consultation_images',
            )
        if 'created_consultation' in locals() and created_consultation:
            _cleanup_vastu_resource(
                repository,
                user_id,
                str(created_consultation.get('_id') or created_consultation.get('id') or ''),
                'vastu_consultations',
            )
        return jsonify({'error': 'Consultation could not be saved. Check storage and try again.'}), 503


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


def calculate_materials(area_per_floor, floors=1):
    quantities = {}
    for key, factor in MATERIAL_FACTORS.items():
        quantity = area_per_floor * factor * max(floors, 1)
        quantities[key] = math.ceil(round(quantity, 10)) if key == 'cement' else round(quantity, 2)
    return quantities


def _positive_measurement(form, key, label, maximum):
    raw_value = form.get(key, '').strip()
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        raise ValueError(f'Enter a valid {label}.')
    if not math.isfinite(value) or value <= 0 or value > maximum:
        raise ValueError(f'{label} must be greater than 0 and no more than {maximum:g}.')
    return value


def _optional_measurement(form, key, label, maximum):
    raw_value = form.get(key, '').strip()
    if not raw_value:
        return 0.0
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        raise ValueError(f'Enter a valid {label}.')
    if not math.isfinite(value) or value < 0 or value > maximum:
        raise ValueError(f'{label} must be between 0 and {maximum:g}.')
    return value


def estimate_brickwork(form):
    wall_length = _positive_measurement(form, 'wall_length_m', 'wall length (m)', 10000)
    wall_height = _positive_measurement(form, 'wall_height_m', 'wall height (m)', 1000)
    wall_thickness = _positive_measurement(form, 'wall_thickness_m', 'wall thickness (m)', 10)
    openings_area = _optional_measurement(form, 'openings_area_m2', 'openings area (m²)', 10000000)
    brick_length = _positive_measurement(form, 'brick_length_mm', 'brick length (mm)', 2000) / 1000
    brick_height = _positive_measurement(form, 'brick_height_mm', 'brick height (mm)', 2000) / 1000
    brick_width = _positive_measurement(form, 'brick_width_mm', 'brick width (mm)', 2000) / 1000
    if brick_width > wall_thickness:
        raise ValueError('Brick width cannot be greater than wall thickness.')
    joint = _positive_measurement(form, 'mortar_joint_mm', 'mortar joint (mm)', 100) / 1000
    cement_ratio = _positive_measurement(form, 'cement_ratio', 'cement mix ratio', 100)
    sand_ratio = _positive_measurement(form, 'sand_ratio', 'sand mix ratio', 100)
    dry_factor = _positive_measurement(form, 'mortar_dry_factor', 'dry-volume factor', 3)
    wastage_percent = _optional_measurement(form, 'wastage_percent', 'wastage percentage', 100)

    gross_wall_area = wall_length * wall_height
    if openings_area >= gross_wall_area:
        raise ValueError('Openings area must be less than the gross wall area.')
    net_wall_volume = (gross_wall_area - openings_area) * wall_thickness

    modular_brick_volume = (brick_length + joint) * (brick_height + joint) * (brick_width + joint)
    brick_count = math.ceil(net_wall_volume / modular_brick_volume)
    actual_brick_volume = brick_length * brick_height * brick_width
    wet_mortar_volume = max(0, net_wall_volume - brick_count * actual_brick_volume)
    wastage_multiplier = 1 + wastage_percent / 100
    dry_mortar_volume = wet_mortar_volume * dry_factor * wastage_multiplier
    ratio_total = cement_ratio + sand_ratio
    cement_volume = dry_mortar_volume * cement_ratio / ratio_total
    sand_volume = dry_mortar_volume * sand_ratio / ratio_total

    return {
        'net_wall_area_m2': round(gross_wall_area - openings_area, 3),
        'net_masonry_volume_m3': round(net_wall_volume, 3),
        'bricks_pieces': math.ceil(brick_count * wastage_multiplier),
        'cement_bags_50kg': math.ceil(round(cement_volume * 1440 / 50, 10)),
        'sand_m3': round(sand_volume, 3),
        'assumptions': (
            f'Modular brick count includes a {joint * 1000:g} mm mortar joint. '
            f'Mortar uses a configurable 1:{sand_ratio:g} cement:sand volume ratio, '
            f'a dry-volume factor of {dry_factor:g}, {wastage_percent:g}% allowance, '
            'and cement bulk density of 1440 kg/m³ for 50 kg bag conversion. '
            'These are editable estimation assumptions, not an approved mix design.'
        ),
    }


def estimate_concrete_volume(form):
    slab_area = _optional_measurement(form, 'slab_area_m2', 'slab area (m²)', 10000000)
    slab_thickness = _optional_measurement(form, 'slab_thickness_mm', 'slab thickness (mm)', 5000) / 1000
    if bool(slab_area) != bool(slab_thickness):
        raise ValueError('Enter both slab area and slab thickness, or leave both blank.')

    component_inputs = (
        ('columns', 'column_count', ('column_width_mm', 'column_depth_mm', 'column_height_m')),
        ('beams', 'beam_count', ('beam_width_mm', 'beam_depth_mm', 'beam_length_m')),
        ('footings', 'footing_count', ('footing_length_mm', 'footing_width_mm', 'footing_depth_mm')),
    )
    component_volumes = {}
    total_volume = slab_area * slab_thickness
    if slab_area:
        component_volumes['slab'] = total_volume

    for label, count_key, dimension_keys in component_inputs:
        raw_values = [form.get(count_key, '').strip()] + [form.get(key, '').strip() for key in dimension_keys]
        if not any(raw_values):
            continue
        if not all(raw_values):
            raise ValueError(f'Enter the count and all dimensions for {label}, or leave them blank.')
        try:
            count = int(raw_values[0])
        except (TypeError, ValueError):
            raise ValueError(f'{label.title()} count must be a whole number.')
        if count <= 0 or count > 100000:
            raise ValueError(f'{label.title()} count must be between 1 and 100000.')
        dimensions = []
        for key in dimension_keys:
            dimension_name, unit = key.rsplit('_', 1)
            label_text = f"{dimension_name.replace('_', ' ')} ({unit})"
            maximum = 5000 if key.endswith('_mm') else 1000
            dimensions.append(_positive_measurement(form, key, label_text, maximum))
        if label == 'columns':
            width, depth, height = dimensions
            volume = count * (width / 1000) * (depth / 1000) * height
        elif label == 'beams':
            width, depth, length = dimensions
            volume = count * (width / 1000) * (depth / 1000) * length
        else:
            length, width, depth = dimensions
            volume = count * (length / 1000) * (width / 1000) * (depth / 1000)
        component_volumes[label] = volume
        total_volume += volume

    if not component_volumes:
        raise ValueError('Enter dimensions for at least one concrete component.')
    return {
        'components_m3': {name: round(volume, 3) for name, volume in component_volumes.items()},
        'total_m3': round(total_volume, 3),
        'assumptions': (
            'Geometric volume only, calculated from the dimensions entered. '
            'No cement, aggregate, or reinforcement quantity is inferred; use the '
            'engineer-approved concrete mix and structural drawings.'
        ),
    }


def calculate_project_estimate(form):
    estimate_phases = []
    subtotal = 0.0
    has_quantities = False

    for phase in PROJECT_ESTIMATE_PHASES:
        phase_items = []
        phase_total = 0.0
        for item in phase['items']:
            quantity_key = f"qty_{item['key']}"
            rate_key = f"rate_{item['key']}"
            quantity_raw = form.get(quantity_key, '').strip()
            rate_raw = form.get(rate_key, '').strip()
            if not quantity_raw:
                continue
            try:
                quantity = float(quantity_raw)
            except (TypeError, ValueError):
                raise ValueError(f"Enter a valid quantity for {item['name']}.")
            if not math.isfinite(quantity) or quantity <= 0 or quantity > 1000000000:
                raise ValueError(f"Quantity for {item['name']} must be greater than 0.")
            if not rate_raw:
                raise ValueError(f"Enter your local unit rate for {item['name']}.")
            try:
                rate = float(rate_raw)
            except (TypeError, ValueError):
                raise ValueError(f"Enter a valid unit rate for {item['name']}.")
            if not math.isfinite(rate) or rate < 0 or rate > 1000000000000:
                raise ValueError(f"Unit rate for {item['name']} must be 0 or greater.")

            amount = round(quantity * rate, 2)
            phase_total += amount
            has_quantities = True
            phase_items.append({
                **item,
                'quantity': round(quantity, 3),
                'rate': round(rate, 2),
                'amount': amount,
            })

        subtotal += phase_total
        estimate_phases.append({
            'key': phase['key'],
            'name': phase['name'],
            'items': phase_items,
            'subtotal': round(phase_total, 2),
        })

    if not has_quantities:
        raise ValueError('Enter at least one measured quantity and its local unit rate.')

    contingency_raw = form.get('contingency_percent', '0').strip() or '0'
    try:
        contingency_percent = float(contingency_raw)
    except (TypeError, ValueError):
        raise ValueError('Enter a valid contingency percentage.')
    if not math.isfinite(contingency_percent) or contingency_percent < 0 or contingency_percent > 100:
        raise ValueError('Contingency must be between 0 and 100 percent.')

    contingency_amount = round(subtotal * contingency_percent / 100, 2)
    return {
        'project_name': (form.get('project_name', '').strip()[:120] or 'Untitled project'),
        'phases': estimate_phases,
        'subtotal': round(subtotal, 2),
        'contingency_percent': contingency_percent,
        'contingency_amount': contingency_amount,
        'grand_total': round(subtotal + contingency_amount, 2),
    }


def _simulation_materials(area, floors=1):
    materials = calculate_materials(area, floors)
    return {
        'area': round(area, 2),
        'floors': max(floors, 1),
        'material_quantities': materials,
        'factors_per_sq_ft_per_floor': MATERIAL_FACTORS,
        'material_units': MATERIAL_UNITS,
        'calculation_basis': (
            'Cement bags = area per floor × floors × 0.45 bags, rounded up to a whole '
            '50 kg bag. Other materials use legacy area factors with unspecified physical units.'
        ),
        'unit_warning': (
            'Cement uses a rough planning assumption, not IS-code quantities. Other legacy '
            'app factors do not define physical output units. This is not a verified bill of '
            'quantities; do not use it as the sole basis for procurement or construction.'
        ),
        'strength_assessment': (
            'Not calculated. Concrete strength needs a specified mix design and verified '
            'laboratory testing; this area-based estimator cannot determine it.'
        ),
        'disclaimer': (
            'Preliminary area-based planning only. This is not an IS-code quantity takeoff, '
            'structural design, material purchase list, or safety assessment.'
        )
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

    base_material_requirement = calculate_materials(built_up_area, 1)
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


@app.before_request
def require_vercel_session_secret():
    auth_endpoints = {'login', 'register', 'forgot_password', 'reset_password', 'verify_account'}
    if os.getenv('VERCEL') == '1' and not SECRET_KEY_CONFIGURED and request.endpoint in auth_endpoints:
        logger.error('Authentication is unavailable because SECRET_KEY is not configured in Vercel.')
        return render_template(
            'error.html',
            code=503,
            message='Authentication is temporarily unavailable. Configure a non-empty SECRET_KEY in Vercel Project Settings, then redeploy.',
        ), 503
    if os.getenv('VERCEL') == '1' and request.endpoint in {'login', 'register'} and not _mongo_available():
        logger.error('Authentication is unavailable because MongoDB is not reachable.')
        return render_template(
            'error.html',
            code=503,
            message='Authentication is temporarily unavailable. Configure MONGO_URI in Vercel Project Settings and ensure MongoDB is reachable.',
        ), 503


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
            role = 'admin' if email.lower() in _effective_admin_email_list() else 'user'
            try:
                users = get_user_store()
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
                        'email_verified': True,
                        'mobile_verified': True,
                        'verification_codes': {},
                        'created_at': datetime.utcnow(),
                    })
                    session['user_id'], session['user_name'], session['user_email'], session['user_role'] = str(result.inserted_id), name, email, role
                else:
                    if users.find_by_email(email):
                        flash('An account with that email already exists.', 'warning')
                        return render_template('auth.html', mode='register')
                    created = users.create_user(name, email, generate_password_hash(password), phone=phone, email_verified=True, mobile_verified=True, role=role)
                    session['user_id'], session['user_name'], session['user_email'], session['user_role'] = str(created['_id']), created['name'], created['email'], created.get('role', 'user')
                flash('Account ready. You can continue to your dashboard.', 'success')
                return redirect(url_for('dashboard'))
            except (PyMongoError, ValueError, DatabaseUnavailableError):
                flash('Database is unavailable. Start MongoDB, then try registering again.', 'danger')
    return render_template('auth.html', mode='register')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        try:
            users = get_user_store()
            if hasattr(users, 'verify_password'):
                record = users.verify_password(email, password)
            else:
                record = users.find_by_email(email)
            if record:
                session['user_id'], session['user_name'], session['user_email'] = (
                    str(record.get('_id') or record.get('id') or ''),
                    record.get('name') or email,
                    record.get('email') or email,
                )
                session['user_role'] = _user_role_from_record(record)
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
        except (PyMongoError, DatabaseUnavailableError):
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
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


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
    total_cost = round(total_built_area * 75, 2)
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


@app.route('/vastu', methods=['GET', 'POST'])
@login_required
def vastu_analysis():
    projects_store = get_project_store()
    custom_rule_repository = get_resource_repository('vastu_rules')
    report_repository = get_resource_repository('vastu_reports')
    admin_rule_repository = get_resource_repository('vastu_admin_rules')
    standard_rules = _configured_admin_vastu_rules(admin_rule_repository)
    standard_rules_by_component = {}
    for standard_rule in standard_rules:
        if isinstance(standard_rule, dict):
            standard_rules_by_component.setdefault(standard_rule.get('component'), []).append(standard_rule)
    display_rules = {}
    for key, default_rule in VASTU_RULES.items():
        configured = standard_rules_by_component.get(key, [])
        active = next((item for item in configured if item.get('enabled', True)), None)
        display_rules[key] = dict(default_rule)
        display_rules[key]['enabled'] = active is not None
        if active:
            display_rules[key].update({
                'preferred': active.get('preferred_direction') or default_rule['preferred'],
                'alternatives': active.get('alternative_directions') or [],
                'weight': active.get('weight') or default_rule['weight'],
                'label': active.get('rule_name') or default_rule['label'],
                'description': active.get('description') or default_rule['description'],
                'recommendation': active.get('recommendation') or default_rule['recommendation'],
                'source': active.get('source') or default_rule['source'],
                'category': active.get('category') or default_rule['category'],
                'applicable_conditions': active.get('applicable_conditions') or default_rule['applicable_conditions'],
            })
            display_rules[key]['preferred_labels'] = [
                DIRECTION_LABELS[item] for item in active.get('preferred_directions', [])
                if item in DIRECTION_LABELS
            ] or [DIRECTION_LABELS[display_rules[key]['preferred']]]
            display_rules[key]['alternative_labels'] = [
                DIRECTION_LABELS[item] for item in display_rules[key]['alternatives']
                if item in DIRECTION_LABELS
            ]
    if hasattr(projects_store, 'find_for_user'):
        projects = projects_store.find_for_user(session['user_id'])
    elif hasattr(projects_store, 'find'):
        projects = list(projects_store.find({'user_id': session['user_id']}))
    else:
        projects = []
    custom_rules = [
        serialize_resource(item)
        for item in custom_rule_repository.list(session['user_id'], resource_type='vastu_rules')
    ]
    saved_reports = [
        serialize_resource(item)
        for item in report_repository.list(session['user_id'], resource_type='vastu_reports')
    ]
    saved_reports.sort(key=lambda item: str(item.get('created_at') or ''), reverse=True)

    project = None
    result = None
    analysis_details = None
    view_report = None
    analysis_mode = 'standard'
    layout_data = {}
    settings = {
        'plot_shape': 'rectangular',
        'north_direction': 'N',
        'unit': 'ft',
        'room_directions': {},
        'guideline_preferences': {
            key: rule['preferred'] for key, rule in display_rules.items()
        },
        'guideline_weights': {
            key: rule['weight'] for key, rule in display_rules.items()
        },
        'analysis_mode': 'standard',
    }

    if request.method == 'POST':
        project_id = (request.form.get('project_id') or '').strip()
        if project_id:
            project = projects_store.find_one({
                'user_id': session['user_id'],
                **project_id_query(project_id),
            }) if hasattr(projects_store, 'find_one') else None
            if not project:
                flash('The selected project was not found.', 'danger')
                return redirect(url_for('vastu_analysis'))

        try:
            if project:
                length = project.get('plot_length')
                width = project.get('plot_width')
                if length is None or width is None:
                    raise ValueError('The selected project does not have valid plot dimensions.')
                unit = project.get('unit', 'ft')
                shape = 'square' if math.isclose(float(length), float(width), rel_tol=0.0, abs_tol=0.01) else 'rectangular'
            else:
                length = request.form.get('plot_length')
                width = request.form.get('plot_width')
                unit = request.form.get('unit', 'ft')
                shape = request.form.get('plot_shape', 'rectangular')

            north_direction = request.form.get('north_direction', '')
            analysis_mode = (request.form.get('analysis_mode') or 'standard').strip().lower()
            if analysis_mode not in {'standard', 'custom', 'combined'}:
                raise ValueError('Choose Standard, Custom, or Combined Vastu mode.')
            if analysis_mode in {'custom', 'combined'} and not any(rule.get('enabled', True) for rule in custom_rules):
                raise ValueError('Create and enable at least one custom rule before choosing Custom or Combined mode.')
            room_directions = {
                key: request.form.get(f'direction_{key}', '').strip()
                for key in display_rules
            }
            guideline_preferences = {
                key: request.form.get(f'guideline_{key}', rule['preferred'])
                for key, rule in display_rules.items()
            }
            guideline_weights = {
                key: request.form.get(f'weight_{key}', rule['weight'])
                for key, rule in display_rules.items()
            }
            for key, direction in room_directions.items():
                if direction and direction not in DIRECTIONS:
                    raise ValueError(f'Choose a valid direction for {display_rules[key]["label"]}.')
            for key, direction in guideline_preferences.items():
                if direction not in DIRECTIONS:
                    raise ValueError(f'Choose a valid preferred guideline for {display_rules[key]["label"]}.')

            layout_data = (project or {}).get('layout_data') or {}
            if isinstance(layout_data, str):
                try:
                    layout_data = json.loads(layout_data)
                except json.JSONDecodeError:
                    layout_data = {}

            result = analyze_vastu(
                length,
                width,
                shape,
                north_direction,
                room_directions,
                guideline_preferences,
                guideline_weights,
                layout_data,
            )
            component_directions = {
                rule['key']: rule['selected_direction']
                for rule in result['rules']
                if rule.get('selected_direction') in DIRECTIONS
            }
            analysis_standard_rules = []
            for rule_group in standard_rules_by_component.values():
                for standard_rule in rule_group:
                    component = standard_rule.get('component')
                    selected_guideline = guideline_preferences.get(
                        component,
                        standard_rule.get('preferred_direction'),
                    )
                    try:
                        weight = float(guideline_weights.get(component, standard_rule.get('weight', 2.0)))
                    except (TypeError, ValueError):
                        weight = float(standard_rule.get('weight') or 2.0)
                    analysis_standard_rules.append({
                        **standard_rule,
                        'preferred': selected_guideline,
                        'preferred_direction': selected_guideline,
                        'preferred_directions': [selected_guideline] if selected_guideline in DIRECTIONS else [],
                        'weight': weight,
                    })
            analysis_details = analyze_rule_sets(
                component_directions,
                custom_rules,
                analysis_mode,
                standard_rules=analysis_standard_rules,
            )
            result['legacy_score'] = result['score']
            result['score'] = analysis_details['score']
            result['analysis_mode'] = analysis_mode
            result['analysis_details'] = analysis_details
            settings = {
                'plot_shape': shape,
                'north_direction': north_direction,
                'unit': unit if unit in {'ft', 'meter'} else 'ft',
                'room_directions': room_directions,
                'guideline_preferences': guideline_preferences,
                'guideline_weights': {
                    key: float(value) for key, value in guideline_weights.items()
                },
                'analysis_mode': analysis_mode,
            }
            if project:
                project_id = str(project.get('_id') or project.get('id'))
                projects_store.update_one(
                    {'user_id': session['user_id'], **project_id_query(project_id)},
                    {'$set': {
                        'vastu_settings': settings,
                        'vastu_analysis': result,
                        'updated_at': datetime.utcnow(),
                    }},
                )
            else:
                project_name = (request.form.get('project_name') or 'Vastu Analysis').strip()[:120]
                saved_project = projects_store.insert_one({
                    'user_id': session['user_id'],
                    'project_name': project_name or 'Vastu Analysis',
                    'plot_length': result['plot_length'],
                    'plot_width': result['plot_width'],
                    'unit': settings['unit'],
                    'floors': 1,
                    'rooms': {},
                    'room_dimensions': {},
                    'built_up_area': round(result['plot_area'] * 0.7, 2),
                    'layout_data': {},
                    'vastu_settings': settings,
                    'vastu_analysis': result,
                    'created_at': datetime.utcnow(),
                    'updated_at': datetime.utcnow(),
                })
                if isinstance(saved_project, dict):
                    project_id = str(saved_project.get('_id') or saved_project.get('id'))
                else:
                    project_id = str(saved_project.inserted_id)
            flash('Vastu analysis saved to your project.', 'success')
            return redirect(url_for('vastu_analysis', project_id=project_id))
        except (TypeError, ValueError) as exc:
            flash(str(exc), 'danger')
            settings.update({
                'plot_shape': request.form.get('plot_shape', settings['plot_shape']),
                'north_direction': request.form.get('north_direction', settings['north_direction']),
                'unit': request.form.get('unit', settings['unit']),
                'room_directions': {
                    key: request.form.get(f'direction_{key}', '')
                    for key in display_rules
                },
                'guideline_preferences': {
                    key: request.form.get(f'guideline_{key}', rule['preferred'])
                    for key, rule in display_rules.items()
                },
                'guideline_weights': {
                    key: request.form.get(f'weight_{key}', rule['weight'])
                    for key, rule in display_rules.items()
                },
                'analysis_mode': request.form.get('analysis_mode', 'standard'),
            })

    else:
        report_id = (request.args.get('report_id') or '').strip()
        if report_id:
            view_report = report_repository.get(session['user_id'], report_id, 'vastu_reports')
            if not view_report:
                flash('Saved Vastu report not found.', 'danger')
                return redirect(url_for('vastu_analysis'))
            view_report = serialize_resource(view_report)
            result = view_report.get('analysis')
            project = {
                '_id': view_report.get('project_id'),
                'project_name': view_report.get('project_name', 'Vastu Analysis'),
                'plot_length': view_report.get('plot_length'),
                'plot_width': view_report.get('plot_width'),
                'unit': view_report.get('unit', 'ft'),
            }
            analysis_details = result.get('analysis_details') if isinstance(result, dict) else None
            analysis_mode = (result or {}).get('analysis_mode', 'standard')
            settings.update((result or {}).get('settings') or {})

        project_id = (request.args.get('project_id') or '').strip()
        if project_id and not view_report:
            project = projects_store.find_one({
                'user_id': session['user_id'],
                **project_id_query(project_id),
            }) if hasattr(projects_store, 'find_one') else None
            if not project:
                flash('The selected project was not found.', 'danger')
                return redirect(url_for('vastu_analysis'))
            settings.update(project.get('vastu_settings') or {})
            result = project.get('vastu_analysis')
            analysis_mode = settings.get('analysis_mode', 'standard')
            analysis_details = (result or {}).get('analysis_details') if isinstance(result, dict) else None

    if project and not view_report:
        settings['unit'] = project.get('unit') if project.get('unit') in {'ft', 'meter'} else 'ft'
        try:
            settings['plot_shape'] = (
                'square'
                if math.isclose(
                    float(project.get('plot_length')),
                    float(project.get('plot_width')),
                    rel_tol=0.0,
                    abs_tol=0.01,
                )
                else 'rectangular'
            )
        except (TypeError, ValueError):
            settings['plot_shape'] = 'rectangular'
        layout_data = project.get('layout_data') or {}
        if isinstance(layout_data, str):
            try:
                layout_data = json.loads(layout_data)
            except json.JSONDecodeError:
                layout_data = {}
    layout_directions = directions_from_layout(layout_data, settings.get('north_direction', 'N'))
    layout_room_items = []
    if isinstance(layout_data, dict):
        for room_name, positions in layout_data.items():
            if not isinstance(positions, list):
                continue
            valid_positions = []
            for position in positions:
                if not isinstance(position, dict):
                    continue
                try:
                    x = float(position.get('x'))
                    y = float(position.get('y'))
                except (TypeError, ValueError):
                    continue
                if math.isfinite(x) and math.isfinite(y) and 0 <= x <= 720 and 0 <= y <= 500:
                    valid_positions.append({'x': round(x, 2), 'y': round(y, 2)})
            if valid_positions:
                room_rule_directions = directions_from_layout(
                    {room_name: valid_positions},
                    settings.get('north_direction', 'N'),
                )
                room_rule = next(iter(room_rule_directions.values()), None)
                layout_room_items.append({
                    'name': str(room_name)[:40],
                    'positions': valid_positions,
                    'direction': room_rule if room_rule in DIRECTIONS else None,
                })
    if result and not analysis_details and isinstance(result, dict):
        stored_rules = result.get('rules', [])
        stored_directions = {
            rule.get('key'): rule.get('selected_direction')
            for rule in stored_rules
            if isinstance(rule, dict) and rule.get('selected_direction') in DIRECTIONS
        }
        analysis_mode = settings.get('analysis_mode', 'standard')
        effective_mode = analysis_mode if analysis_mode in {'standard', 'custom', 'combined'} else 'standard'
        applicable_custom_rules = custom_rules if effective_mode in {'custom', 'combined'} else []
        stored_standard_rules = []
        for rule in standard_rules:
            component = rule.get('component')
            preferred = settings.get('guideline_preferences', {}).get(
                component,
                rule.get('preferred_direction') or rule.get('preferred'),
            )
            weight = settings.get('guideline_weights', {}).get(component, rule.get('weight', 2.0))
            try:
                weight = float(weight)
            except (TypeError, ValueError):
                weight = float(rule.get('weight') or 2.0)
            stored_standard_rules.append({
                **rule,
                'preferred': preferred,
                'preferred_direction': preferred,
                'preferred_directions': [preferred] if preferred in DIRECTIONS else [],
                'weight': weight,
            })
        analysis_details = analyze_rule_sets(
            stored_directions,
            applicable_custom_rules,
            effective_mode,
            standard_rules=stored_standard_rules,
        )
    if view_report:
        layout_data = {}
        layout_directions = {}
        layout_room_items = []

    return render_template(
        'vastu.html',
        projects=projects,
        project=project,
        result=result,
        settings=settings,
        rules=display_rules,
        directions=DIRECTIONS,
        direction_labels=DIRECTION_LABELS,
        layout_directions=layout_directions,
        layout_data=layout_data,
        layout_room_items=layout_room_items,
        component_options=VASTU_COMPONENTS,
        custom_rules=custom_rules,
        saved_reports=saved_reports,
        analysis_details=analysis_details,
        analysis_mode=analysis_mode,
        view_report=view_report,
    )


@app.route('/vastu/<project_id>/report.pdf')
@login_required
def vastu_report_pdf(project_id):
    projects_store = get_project_store()
    project = projects_store.find_one({
        'user_id': session['user_id'],
        **project_id_query(project_id),
    }) if hasattr(projects_store, 'find_one') else None
    analysis = project.get('vastu_analysis') if project else None
    if not analysis:
        return render_template('error.html', code=404, message='Vastu analysis not found for this project.'), 404

    return _build_vastu_report_pdf(project, analysis, 'vishwakarma-vastu-report.pdf')


@app.route('/vastu/reports/<report_id>.pdf')
@login_required
def saved_vastu_report_pdf(report_id):
    report_repository = get_resource_repository('vastu_reports')
    report = report_repository.get(session['user_id'], report_id, 'vastu_reports')
    if not report:
        return render_template('error.html', code=404, message='Saved Vastu report not found.'), 404
    report = serialize_resource(report)
    project = {
        'project_name': report.get('project_name', 'Vastu Analysis'),
        'unit': report.get('unit', 'ft'),
    }
    return _build_vastu_report_pdf(project, report.get('analysis') or {}, 'vishwakarma-saved-vastu-report.pdf')


def _build_vastu_report_pdf(project, analysis, download_name):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    import textwrap

    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4)
    page_height = A4[1]
    y = page_height - 54

    def write_line(text, font='Helvetica', size=10, gap=16):
        nonlocal y
        pdf.setFont(font, size)
        printable_text = str(text).encode('latin-1', 'replace').decode('latin-1')
        for line in textwrap.wrap(printable_text, width=96) or ['']:
            if y < 54:
                pdf.showPage()
                y = page_height - 54
            pdf.drawString(48, y, line)
            y -= gap

    pdf.setTitle('Vishwakarma Vastu Analysis Report')
    write_line('Project name: Vishwakarma', 'Helvetica-Bold', 18, 24)
    write_line('Vastu Shastra Analysis Report', 'Helvetica-Bold', 14, 22)
    write_line(f"Plan: {project.get('project_name', 'Untitled')}")
    plot_length = analysis.get('plot_length')
    plot_width = analysis.get('plot_width')
    if plot_length is not None and plot_width is not None:
        write_line(
            f"Plot: {plot_length:g} x {plot_width:g} {project.get('unit', 'ft')} "
            f"({analysis.get('plot_shape', 'not specified')})"
        )
    write_line(f"North direction: {analysis.get('north_label', 'not provided')}")
    details = analysis.get('analysis_details') or {}
    score_value = details.get('score', analysis.get('score'))
    score = f"{score_value}/100" if score_value is not None else 'Not available - insufficient direction data'
    write_line(f"Application-defined rule-match score: {score}")
    if details:
        write_line(f"Analysis mode: {details.get('mode', analysis.get('analysis_mode', 'standard'))}")
        write_line(
            f"Matches: {details.get('matches', 0)} | Partially matches: {details.get('partial_matches', 0)} | "
            f"Differs: {details.get('differs', 0)} | Insufficient data: {details.get('insufficient', 0)}"
        )
        write_line('Calculation method', 'Helvetica-Bold', 11, 18)
        write_line(details.get('calculation_method', 'Application-defined weighted rule comparison.'))
        write_line('Rules applied and room-wise results', 'Helvetica-Bold', 11, 18)
        for rule in details.get('rules', []):
            preferred = ', '.join(rule.get('preferred_labels', [])) or 'not configured'
            alternatives = ', '.join(rule.get('alternative_labels', [])) or 'none configured'
            write_line(
                f"{rule.get('rule_name', 'Rule')} / {rule.get('component_label', 'Component')}: "
                f"{rule.get('actual_direction_label', 'Insufficient data')} - {rule.get('status_label', 'Unknown')} "
                f"(preferred: {preferred}; alternatives: {alternatives}). {rule.get('explanation', '')}"
            )
            if rule.get('category'):
                write_line(f"Category: {rule['category']}")
            write_line(f"Source/reference: {rule.get('source', 'Not provided')}")
            if rule.get('applicable_conditions'):
                write_line(f"Applicable conditions: {rule['applicable_conditions']}")
            if rule.get('recommendation'):
                write_line(f"Recommendation: {rule['recommendation']}")
        write_line('Conflicting rules', 'Helvetica-Bold', 11, 18)
        for conflict in details.get('conflicts', []):
            write_line(f"{conflict.get('label', 'Component')}: {', '.join(conflict.get('rule_names', []))}")
        if not details.get('conflicts'):
            write_line('No conflicting preferred directions were identified.')
        suggestions = [rule for rule in details.get('rules', []) if rule.get('status') != 'matches']
        write_line('Suggestions and missing information', 'Helvetica-Bold', 11, 18)
        for rule in suggestions:
            write_line(f"{rule.get('component_label', 'Component')}: {rule.get('explanation', '')}")
            if rule.get('recommendation'):
                write_line(rule['recommendation'])
    else:
        write_line(
            f"Matched: {analysis.get('matched_count', 0)} | Needs review: {analysis.get('needs_review_count', 0)} | "
            f"Missing: {analysis.get('missing_count', 0)} | Coverage: {analysis.get('coverage_percent', 0)}%"
        )
        write_line('Calculation method', 'Helvetica-Bold', 11, 18)
        write_line(analysis.get('calculation_method', 'Weighted comparison of entered directions.'))
        write_line('Room-wise analysis', 'Helvetica-Bold', 11, 18)
        for rule in analysis.get('rules', []):
            write_line(
                f"{rule['label']}: {rule['selected_label']} - {rule['status'].replace('_', ' ').title()} "
                f"(preferred: {rule['preferred_label']}, weight: {rule['weight']:g}). {rule['recommendation']}"
            )
        write_line('Suggested improvements', 'Helvetica-Bold', 11, 18)
        suggestions = [rule for rule in analysis.get('rules', []) if rule['status'] != 'matched']
        if suggestions:
            for rule in suggestions:
                alternatives = ', '.join(rule['alternative_labels']) or 'No alternatives configured'
                write_line(f"{rule['label']}: {rule['recommendation']} Alternatives: {alternatives}.")
        else:
            write_line('No review suggestions for the directions provided.')
    write_line('Disclaimer', 'Helvetica-Bold', 11, 18)
    write_line(analysis.get('disclaimer', (
        'Vastu guidance is a traditional or user-defined preference, not a scientifically proven prediction. '
        'This score does not determine house quality, safety, health, wealth, or luck.'
    )))
    write_line('This report is cultural and educational guidance only; it is not scientific prediction, architectural approval, or construction safety advice.')
    pdf.save()
    stream.seek(0)
    return send_file(
        stream,
        as_attachment=True,
        download_name=download_name,
        mimetype='application/pdf',
    )


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
            layout_valid = True
            architectural_elements = []
            try:
                layout_data = json.loads(request.form.get('layout_data') or '{}')
                if not isinstance(layout_data, dict):
                    raise ValueError('Room layout data is invalid.')
                cleaned_layout = {}
                for room, positions in layout_data.items():
                    if room not in ROOMS or not isinstance(positions, list):
                        raise ValueError('Room layout data is invalid.')
                    cleaned_positions = []
                    for position in positions:
                        if not isinstance(position, dict):
                            raise ValueError('Room layout data is invalid.')
                        x, y = float(position.get('x')), float(position.get('y'))
                        if not math.isfinite(x) or not math.isfinite(y) or not (0 <= x <= 720 and 0 <= y <= 500):
                            raise ValueError('A room position is outside the planner canvas.')
                        cleaned_positions.append({'x': round(x, 2), 'y': round(y, 2)})
                    cleaned_layout[room] = cleaned_positions
                layout_data = cleaned_layout

                raw_elements = json.loads(request.form.get('architectural_elements') or '[]')
                if not isinstance(raw_elements, list) or len(raw_elements) > 500:
                    raise ValueError('Architectural element data is invalid.')
                for element in raw_elements:
                    if not isinstance(element, dict) or element.get('room') not in ROOMS:
                        raise ValueError('Architectural element data is invalid.')
                    room = element['room']
                    room_index = int(element.get('room_index', -1))
                    if room_index < 0 or room_index >= int(safe_float(request.form.get('room_' + room), 0)):
                        raise ValueError('An architectural element references a room that is not in this plan.')
                    kind = element.get('kind')
                    if kind not in {'door', 'window', 'ventilator', 'skylight', 'furniture', 'stairs'}:
                        raise ValueError('Architectural element type is invalid.')
                    room_width = safe_float(request.form.get(f'room_width_{room}'), ROOM_DIMENSIONS.get(room, {}).get('width', 12))
                    room_depth = safe_float(request.form.get(f'room_depth_{room}'), ROOM_DIMENSIONS.get(room, {}).get('depth', 10))
                    room_height = safe_float(request.form.get(f'room_height_{room}'), 9)
                    clean_element = {
                        'id': str(element.get('id', ''))[:80],
                        'kind': kind,
                        'name': str(element.get('name', kind.title()))[:80],
                        'room': room,
                        'room_index': room_index,
                        'floor': max(0, min(floors - 1, int(safe_float(element.get('floor'), 0)))),
                        'slot': max(0, min(20, int(safe_float(element.get('slot'), 0)))),
                    }
                    for field, maximum in (('x', room_width), ('y', room_depth)):
                        value = safe_float(element.get(field), -1)
                        if value < 0 or value > maximum:
                            raise ValueError('An architectural element position is outside its room.')
                        clean_element[field] = round(value, 2)
                    for field, maximum in (('width', room_width), ('depth', room_depth), ('height', room_height)):
                        value = safe_float(element.get(field), 0)
                        if value <= 0 or value > maximum:
                            raise ValueError('Architectural element dimensions must be greater than zero and fit the plot.')
                        clean_element[field] = round(value, 2)
                    if clean_element['x'] + clean_element['width'] > room_width or clean_element['y'] + clean_element['depth'] > room_depth:
                        raise ValueError('An architectural element extends outside its room.')
                    clean_element['rotation'] = int(safe_float(element.get('rotation'), 0)) % 360
                    architectural_elements.append(clean_element)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                flash(str(exc) or 'Room layout data is invalid.', 'danger')
                layout_data = {}
                architectural_elements = []
                layout_valid = False

            area = length * width
            coverage = min(area * 0.7, area)
            selected = {room: int(safe_float(request.form.get('room_' + room), 0)) for room in ROOMS if safe_float(request.form.get('room_' + room), 0) > 0}
            room_dimensions = {}
            for room in ROOMS:
                width_value = safe_float(request.form.get(f'room_width_{room}'), ROOM_DIMENSIONS.get(room, {}).get('width', 12))
                depth_value = safe_float(request.form.get(f'room_depth_{room}'), ROOM_DIMENSIONS.get(room, {}).get('depth', 10))
                height_value = safe_float(request.form.get(f'room_height_{room}'), 9)
                if not 4 <= height_value <= 30:
                    flash(f'{room} wall height must be between 4 and 30 {request.form.get("unit", "ft")}.', 'danger')
                    layout_valid = False
                    height_value = 9
                room_dimensions[room] = {
                    'width': round(width_value, 1) if width_value else round(ROOM_DIMENSIONS.get(room, {}).get('width', 12), 1),
                    'depth': round(depth_value, 1) if depth_value else round(ROOM_DIMENSIONS.get(room, {}).get('depth', 10), 1),
                    'height': round(height_value, 1),
                }
            result = {'length': length, 'width': width, 'unit': request.form.get('unit', 'ft'), 'floors': floors, 'area': round(area, 2), 'built_up': round(coverage * floors, 2), 'open_area': round(area - coverage, 2), 'selected': selected, 'room_dimensions': room_dimensions, 'layout_data': layout_data, 'architectural_elements': architectural_elements}
            if request.form.get('save_project') and layout_valid:
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
                        'layout_data': layout_data,
                        'architectural_elements': architectural_elements,
                        'material_estimate': calculate_materials(result['built_up'], 1),
                        'material_estimate_units': MATERIAL_UNITS,
                        'material_estimate_basis': (
                            'Cement estimate uses 0.45 50 kg bags per sq ft per floor, rounded '
                            'up. Other legacy area factors have unspecified physical units; this '
                            'is not an IS-code quantity takeoff.'
                        ),
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
                            'layout_data': layout_data,
                            'architectural_elements': architectural_elements,
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
            'room_dimensions': project.get('room_dimensions', {}) or {},
            'layout_data': project.get('layout_data', {}) or {},
            'architectural_elements': project.get('architectural_elements', []) or [],
        }

    return render_template('planner.html', result=result, project=project)


@app.route('/structural-design')
@login_required
def structural_design():
    project_store = get_project_store()
    if hasattr(project_store, 'find_for_user'):
        owned_projects = project_store.find_for_user(session['user_id'])
    elif hasattr(project_store, 'find'):
        owned_projects = list(project_store.find({'user_id': session['user_id']}).sort('updated_at', -1))
    else:
        owned_projects = []
    project_options = [
        {
            'id': str(item.get('_id') or item.get('id') or ''),
            'name': str(item.get('project_name') or 'Untitled project'),
            'plot_length': item.get('plot_length', 30),
            'plot_width': item.get('plot_width', 40),
            'unit': item.get('unit', 'ft'),
            'floors': item.get('floors', 1),
            'rooms': item.get('rooms') or {},
            'room_dimensions': item.get('room_dimensions') or {},
            'layout_data': item.get('layout_data') or {},
            'architectural_elements': item.get('architectural_elements') or [],
        }
        for item in owned_projects
    ]
    requested_project_id = request.args.get('project_id')
    project = next(
        (item for item in project_options if item['id'] == str(requested_project_id)),
        project_options[0] if project_options else None,
    )
    if requested_project_id and (not project or project['id'] != str(requested_project_id)):
        return render_template('error.html', code=404, message='Project not found.'), 404

    designs = []
    active_design = None
    if project:
        repository = get_resource_repository('structural_designs')
        designs = [
            serialize_resource(item)
            for item in repository.list(
                session['user_id'], project['id'], 'structural_designs'
            )
        ]
        requested_design_id = request.args.get('design_id')
        active_design = next(
            (item for item in designs if item.get('id') == requested_design_id),
            designs[0] if designs else None,
        )
    return render_template(
        'structural_design.html',
        projects=project_options,
        project=project,
        designs=designs,
        active_design=active_design,
    )


@app.route('/structural-design/drawing/<design_id>.pdf')
@login_required
def structural_design_drawing_pdf(design_id):
    repository = get_resource_repository('structural_designs')
    design_record = repository.get(session['user_id'], design_id, 'structural_designs')
    design_record = serialize_resource(design_record)
    if not design_record:
        return render_template('error.html', code=404, message='Structural drawing not found.'), 404
    project_store = get_project_store()
    project = project_store.find_one({
        'user_id': session['user_id'],
        **project_id_query(design_record.get('project_id')),
    }) if design_record.get('project_id') and hasattr(project_store, 'find_one') else None
    if not project:
        return render_template('error.html', code=404, message='Project not found.'), 404

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    import unicodedata

    data = design_record.get('design_data') or {}
    unit = 'm' if project.get('unit') == 'meter' else 'ft'
    plot_length = max(safe_float(project.get('plot_length'), 30), 0.1)
    plot_width = max(safe_float(project.get('plot_width'), 40), 0.1)
    footing_length = max(safe_float(data.get('footing_length'), 1.5), 0.1)
    footing_width = max(safe_float(data.get('footing_width'), 1.5), 0.1)
    footing_depth = max(safe_float(data.get('footing_depth'), 0.45), 0.1)
    foundation_depth = max(safe_float(data.get('foundation_depth'), 0.9), footing_depth)
    column_width = max(safe_float(data.get('column_width'), 0.3), 0.1)
    column_depth = max(safe_float(data.get('column_depth'), 0.3), 0.1)
    footing_count = max(1, int(safe_float(data.get('footing_count'), 4)))

    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4)
    page_width, page_height = A4
    def pdf_text(value):
        return unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode('ascii')

    pdf.setTitle(f"{pdf_text(design_record.get('name', 'Structural drawing'))} - preliminary")

    def page_header(view_title):
        pdf.setFont('Helvetica-Bold', 15)
        pdf.drawString(40, page_height - 45, 'VISHWAKARMA | STRUCTURAL DESIGN STUDIO')
        pdf.setFont('Helvetica', 10)
        pdf.drawString(40, page_height - 65, f"{pdf_text(project.get('project_name', 'Project'))} - {view_title}")
        pdf.setStrokeColorRGB(0.20, 0.35, 0.50)
        pdf.line(40, page_height - 75, page_width - 40, page_height - 75)

    def dimension(x1, y1, x2, y2, label):
        pdf.setStrokeColorRGB(0.22, 0.40, 0.58)
        pdf.setLineWidth(0.7)
        pdf.line(x1, y1, x2, y2)
        pdf.setFillColorRGB(0.10, 0.23, 0.36)
        pdf.setFont('Helvetica', 8)
        pdf.drawCentredString((x1 + x2) / 2, (y1 + y2) / 2 + 4, label)

    page_header('Foundation plan / top view')
    scale = min(360 / plot_length, 360 / plot_width)
    origin_x, origin_y = 90, 360
    pdf.setStrokeColorRGB(0.08, 0.18, 0.30)
    pdf.setLineWidth(1.2)
    pdf.rect(origin_x, origin_y, plot_length * scale, plot_width * scale)
    columns = max(1, math.ceil(math.sqrt(footing_count)))
    rows = math.ceil(footing_count / columns)
    pdf.setFillColorRGB(0.80, 0.88, 0.96)
    pdf.setStrokeColorRGB(0.10, 0.30, 0.50)
    for index in range(footing_count):
        column_index, row_index = index % columns, index // columns
        x = origin_x + (column_index + 0.5) * plot_length * scale / columns
        y = origin_y + (row_index + 0.5) * plot_width * scale / rows
        fw, fd = footing_length * scale, footing_width * scale
        pdf.rect(x - fw / 2, y - fd / 2, fw, fd, fill=1)
        pdf.setFillColorRGB(0.16, 0.28, 0.40)
        pdf.rect(x - column_width * scale / 2, y - column_depth * scale / 2,
                 column_width * scale, column_depth * scale, fill=1)
        pdf.setFillColorRGB(0.80, 0.88, 0.96)
    dimension(origin_x, origin_y - 24, origin_x + plot_length * scale, origin_y - 24,
              f'Plot length: {plot_length:g} {unit}')
    dimension(origin_x - 20, origin_y, origin_x - 20, origin_y + plot_width * scale,
              f'Plot width: {plot_width:g} {unit}')
    pdf.setFont('Helvetica', 9)
    pdf.drawString(40, 280, f"Footing: {footing_length:g} x {footing_width:g} {unit}; count: {footing_count}")
    pdf.drawString(40, 265, f"Column: {column_width:g} x {column_depth:g} {unit}; concrete: {data.get('foundation_concrete_grade', 'M20')}")
    pdf.drawString(40, 250, f"Footing type: {str(data.get('footing_type', 'isolated')).replace('_', ' ').title()}")
    pdf.setFillColorRGB(0.65, 0.15, 0.12)
    pdf.setFont('Helvetica-Bold', 9)
    pdf.drawString(40, 210, 'SCHEMATIC ONLY - verify geometry, loads, soil data and reinforcement with a licensed engineer.')

    pdf.showPage()
    page_header('Foundation section / reinforcement schematic')
    detail_scale = min(240 / max(footing_length, footing_width), 150 / foundation_depth)
    center_x, base_y = page_width / 2, 290
    fw, fd = footing_length * detail_scale, footing_depth * detail_scale
    pdf.setStrokeColorRGB(0.12, 0.27, 0.42)
    pdf.setFillColorRGB(0.84, 0.90, 0.95)
    pdf.rect(center_x - fw / 2, base_y, fw, fd, fill=1)
    col_w, col_d = column_width * detail_scale, column_depth * detail_scale
    pdf.rect(center_x - col_w / 2, base_y + fd, col_w, 120, fill=1)
    pdf.setStrokeColorRGB(0.72, 0.16, 0.13)
    bar_count = max(2, int(safe_float(data.get('footing_main_bars_x'), 4)))
    for index in range(bar_count):
        x = center_x - fw / 2 + (index + 0.5) * fw / bar_count
        pdf.circle(x, base_y + 7, 2.2, fill=1)
    dimension(center_x - fw / 2, base_y - 22, center_x + fw / 2, base_y - 22,
              f'{footing_length:g} {unit}')
    dimension(center_x + fw / 2 + 20, base_y, center_x + fw / 2 + 20, base_y + fd,
              f'{footing_depth:g} {unit}')
    pdf.setFillColorRGB(0.10, 0.18, 0.28)
    pdf.setFont('Helvetica', 9)
    pdf.drawString(40, 235, f"Excavation depth entered: {foundation_depth:g} {unit}")
    pdf.drawString(40, 218, f"PCC thickness: {safe_float(data.get('pcc_thickness'), 0.1):g} {unit}")
    pdf.drawString(40, 201, f"Reinforcement marks shown schematically; no bar anchorage, cover or code checks are performed.")
    pdf.drawString(40, 60, 'Schematic only; printed scale is not for setting-out. Dimension labels govern.')
    pdf.save()
    stream.seek(0)
    filename = re.sub(r'[^A-Za-z0-9_-]+', '-', design_record.get('name') or 'structural-drawing').strip('-')
    return send_file(stream, as_attachment=True, download_name=f'{filename or "structural-drawing"}.pdf',
                     mimetype='application/pdf')


@app.route('/materials', methods=['GET', 'POST'])
@login_required
def materials():
    area = safe_float(request.form.get('built_up_area')) if request.method == 'POST' else 0
    floors = int(safe_float(request.form.get('floors'), 1) or 1) if request.method == 'POST' else 1
    estimate = calculate_materials(area, floors) if area else None
    brickwork_estimate = None
    concrete_estimate = None
    detail_error = None
    if request.method == 'POST':
        estimate_type = request.form.get('estimate_type')
        try:
            if estimate_type == 'brickwork':
                brickwork_estimate = estimate_brickwork(request.form)
            elif estimate_type == 'concrete':
                concrete_estimate = estimate_concrete_volume(request.form)
        except ValueError as error:
            detail_error = str(error)
    return render_template(
        'materials.html',
        estimate=estimate,
        brickwork_estimate=brickwork_estimate,
        concrete_estimate=concrete_estimate,
        detail_error=detail_error,
        area=area,
        floors=floors,
        factors=MATERIAL_FACTORS,
        units=MATERIAL_UNITS,
        total_estimated_area=area * floors,
    )


MATERIAL_PRICE_OWNER = 'vishwakarma-official'


def _material_estimation_repository(resource_type):
    return get_resource_repository(resource_type)


def _material_price_records():
    repository = _material_estimation_repository('material_price')
    return [serialize_resource(item) for item in repository.list(
        MATERIAL_PRICE_OWNER, resource_type='material_price'
    )]


def _material_location_records():
    repository = _material_estimation_repository('material_location')
    return [serialize_resource(item) for item in repository.list(
        MATERIAL_PRICE_OWNER, resource_type='material_location'
    )]


def _material_catalog_records():
    repository = _material_estimation_repository('material_catalog')
    return [serialize_resource(item) for item in repository.list(
        MATERIAL_PRICE_OWNER, resource_type='material_catalog'
    )]


def _material_estimation_settings():
    repository = _material_estimation_repository('material_config')
    records = repository.list(MATERIAL_PRICE_OWNER, resource_type='material_config')
    return serialize_resource(records[0]) if records else {
        'wastage_percent': 5,
        'dry_volume_factor': DRY_VOLUME_FACTOR,
        'water_cement_ratio': 0.5,
        'mix_ratios': MIX_RATIOS,
    }


def _material_location_options(location_records):
    districts = set(UTTARAKHAND_DISTRICTS)
    villages = {}
    states = {'Uttarakhand'}
    for location in location_records:
        if location.get('state'):
            states.add(location['state'])
        if location.get('district'):
            districts.add(location['district'])
        if location.get('district') and location.get('locality'):
            villages.setdefault(location['district'], set()).add(location['locality'])
    return {
        'states': sorted(states),
        'districts': sorted(districts),
        'villages': {district: sorted(names) for district, names in villages.items()},
    }


@app.route('/material-estimation')
@login_required
def material_estimation():
    try:
        prices = _material_price_records()
        locations = _material_location_records()
        catalog = _material_catalog_records()
        settings = _material_estimation_settings()
        repository = _material_estimation_repository('estimation_history')
        history = [serialize_resource(item) for item in repository.list(
            session['user_id'], resource_type='estimation_history'
        )[:25]]
    except (DatabaseUnavailableError, PyMongoError) as exc:
        logger.exception('Unable to load material estimator data.')
        return render_template(
            'material_estimation.html',
            load_error='Pricing or estimation storage is unavailable. Try again after checking the database.',
            prices=[],
            material_catalog=[],
            price_labels=PRICE_LABELS,
            location_options=_material_location_options([]),
            settings={
                'wastage_percent': 5,
                'dry_volume_factor': DRY_VOLUME_FACTOR,
                'water_cement_ratio': 0.5,
                'mix_ratios': MIX_RATIOS,
            },
            history=[],
        ), 503
    return render_template(
        'material_estimation.html',
        load_error=None,
        prices=prices,
        material_catalog=catalog,
        location_options=_material_location_options(locations),
        settings=settings,
        price_labels=PRICE_LABELS,
        history=history,
    )


@app.route('/api/material-estimation/calculate', methods=['POST'])
@login_required
def material_estimation_calculate():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'Send estimation inputs as a JSON object.'}), 400
    try:
        prices = _material_price_records()
        payload['custom_material_catalog'] = _material_catalog_records()
        settings = _material_estimation_settings()
        payload['configured_mix_ratios'] = settings.get('mix_ratios', MIX_RATIOS)
        payload.setdefault('wastage_percent', settings.get('wastage_percent', 5))
        payload.setdefault('dry_volume_factor', settings.get('dry_volume_factor', DRY_VOLUME_FACTOR))
        estimate = calculate_advanced_estimate(payload, prices)
        repository = _material_estimation_repository('estimation_history')
        saved = repository.create({
            'user_id': str(session['user_id']),
            'resource_type': 'estimation_history',
            'project_name': estimate['project']['name'],
            'location': estimate['pricing_location'],
            'estimate': estimate,
            'created_at': datetime.utcnow().isoformat(),
        })
        return jsonify({'estimate': estimate, 'history_id': str(saved.get('_id') or saved.get('id'))})
    except EstimationError as exc:
        return jsonify({'error': str(exc)}), 400
    except (DatabaseUnavailableError, PyMongoError):
        logger.exception('Material estimation persistence failed.')
        return jsonify({'error': 'Estimation storage is unavailable; the estimate was not saved.'}), 503


@app.route('/api/material-estimation/history')
@login_required
def material_estimation_history():
    try:
        repository = _material_estimation_repository('estimation_history')
        items = repository.list(session['user_id'], resource_type='estimation_history')[:50]
        return jsonify({'items': [serialize_resource(item) for item in items]})
    except (DatabaseUnavailableError, PyMongoError):
        logger.exception('Unable to load estimation history.')
        return jsonify({'error': 'Estimation history is unavailable.'}), 503


@app.route('/material-estimation/<history_id>/report.pdf')
@login_required
def material_estimation_report_pdf(history_id):
    try:
        repository = _material_estimation_repository('estimation_history')
        record = repository.get(session['user_id'], history_id, 'estimation_history')
        if not record:
            return 'Estimation report not found.', 404
        estimate = record.get('estimate') or {}
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from xml.sax.saxutils import escape
        import unicodedata

        def pdf_text(value):
            text = str(value).replace('×', ' x ').replace('÷', ' / ').replace('₹', 'INR ')
            text = text.replace('—', '-').replace('–', '-').replace('•', '-').replace('Ø', 'dia ')
            return escape(unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii'))

        stream = io.BytesIO()
        pdf = SimpleDocTemplate(stream, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm,
                                topMargin=16 * mm, bottomMargin=16 * mm)
        styles = getSampleStyleSheet()
        story = [
            Paragraph('<b>VISHWAKARMA</b> | Material Estimation Report', styles['Title']),
            Paragraph(f"Project: {pdf_text(record.get('project_name') or 'Untitled project')}", styles['Heading2']),
        ]
        location = estimate.get('pricing_location') or {}
        story.extend([
            Paragraph('Location: ' + pdf_text(', '.join(filter(None, (
                location.get('locality'), location.get('district'), location.get('state'), location.get('country')
            )))), styles['BodyText']),
            Paragraph(
                f"Built-up area: {estimate.get('project', {}).get('built_up_area_sqft', 'Not provided')} sq ft",
                styles['BodyText'],
            ),
            Paragraph(f"Generated: {pdf_text(record.get('created_at') or '')}", styles['BodyText']),
            Spacer(1, 8),
            Paragraph('Material quantity and cost summary', styles['Heading2']),
        ])
        rows = [['Material', 'Quantity', 'Location rate', 'Amount', 'Price source']]
        for key, material in (estimate.get('materials') or {}).items():
            rate = material.get('rate')
            rows.append([
                pdf_text(key.replace('_', ' ').title()),
                f"{material.get('quantity', 0)} {material.get('unit', '')}",
                f"INR {rate:,.2f}" if rate is not None else 'Not available',
                f"INR {material['amount']:,.2f}" if material.get('amount') is not None else 'Not priced',
                pdf_text(
                    (material.get('source') or 'No verified rate')
                    + (f" ({material.get('level')} rate)" if material.get('level') else '')
                ),
            ])
        table = Table(rows, repeatRows=1, colWidths=[33 * mm, 34 * mm, 31 * mm, 30 * mm, 48 * mm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#243b53')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#ccd5df')),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f2f5f8')]),
        ]))
        story.extend([table, Spacer(1, 8), Paragraph('Component-wise calculation details', styles['Heading2'])])
        for component in estimate.get('components', []):
            component_quantities = []
            if component.get('wet_volume_m3') is not None:
                concrete = component.get('concrete') or {}
                component_quantities.append(
                    f"wet concrete {component['wet_volume_m3']} m³; "
                    f"{concrete.get('cement_bags', 0)} cement bags; "
                    f"{concrete.get('sand_cft', 0)} CFT sand; "
                    f"{concrete.get('aggregate_cft', 0)} CFT aggregate; "
                    f"{concrete.get('water_litres', 0)} L water"
                )
            for key, label, unit in (
                ('bricks', 'bricks', 'pieces'), ('cement_bags', 'cement', 'bags'),
                ('sand_cft', 'sand', 'CFT'), ('tiles_sq_ft', 'tiles', 'sq ft'),
                ('paint_litres', 'paint', 'litres'),
            ):
                if component.get(key) is not None:
                    component_quantities.append(f"{component[key]} {label} {unit}")
            dimensions = ', '.join(
                f'{key}={value}' for key, value in (component.get('dimensions') or {}).items()
            )
            component_quantities.append(f"quantity {component.get('quantity', 1)}")
            if dimensions:
                component_quantities.append(f"dimensions: {dimensions}")
            breakdown = '; '.join(component_quantities) or 'No material quantity output'
            story.append(Paragraph(
                f"<b>{pdf_text(component.get('name', 'Component'))}</b> "
                f"({pdf_text(component.get('type', ''))}) - "
                f"{pdf_text(breakdown)}. "
                f"{pdf_text(component.get('formula', (component.get('concrete') or {}).get('formula', '')))}",
                styles['BodyText'],
            ))
        if estimate.get('steel_bbs'):
            story.append(Paragraph('Preliminary bar bending schedule', styles['Heading2']))
            bbs_rows = [['Component', 'Dia (mm)', 'Bars', 'Total length (m)', 'Weight (kg)']]
            for bar in estimate['steel_bbs']:
                bbs_rows.append([
                    pdf_text(bar['component']), str(bar['diameter_mm']), str(bar['bar_count']),
                    str(bar['total_length_m']), str(bar['weight_kg']),
                ])
            story.append(Table(bbs_rows, repeatRows=1))
        costs = estimate.get('costs') or {}
        story.extend([
            Spacer(1, 8),
            Paragraph('Cost summary', styles['Heading2']),
            Paragraph(
                f"Materials: INR {costs.get('material_cost', 0):,.2f} | "
                f"Labour: {costs.get('labour_cost') if costs.get('labour_cost') is not None else 'Not priced'} | "
                f"Transportation: {costs.get('transportation_cost') if costs.get('transportation_cost') is not None else 'Not priced'} | "
                f"Other materials: INR {costs.get('other_material_cost', 0):,.2f} | "
                f"Equipment: INR {costs.get('equipment_cost', 0):,.2f} | "
                f"Other: INR {costs.get('other_expenses', 0):,.2f}",
                styles['BodyText'],
            ),
            Paragraph(
                'Labour rate: ' + pdf_text((estimate.get('service_prices', {}).get('labour') or {}).get('rate', 'Not set'))
                + ' - ' + pdf_text((estimate.get('service_prices', {}).get('labour') or {}).get('source', 'No source'))
                + ' | Transportation rate: '
                + pdf_text((estimate.get('service_prices', {}).get('transportation') or {}).get('rate', 'Not set'))
                + ' - ' + pdf_text((estimate.get('service_prices', {}).get('transportation') or {}).get('source', 'No source')),
                styles['BodyText'],
            ),
            Paragraph(
                pdf_text(
                    f"Known total: INR {costs.get('known_total', 0):,.2f} "
                    f"({'Complete' if costs.get('complete') else 'Partial - missing rates: ' + ', '.join(costs.get('unpriced_items', []))})"
                ),
                styles['Heading3'],
            ),
            Paragraph(f"Cost per sq ft: {costs.get('cost_per_sq_ft') if costs.get('cost_per_sq_ft') is not None else 'N/A'} | "
                      f"Cost per sq m: {costs.get('cost_per_sq_m') if costs.get('cost_per_sq_m') is not None else 'N/A'}",
                      styles['BodyText']),
            Paragraph(f"Price update date: {pdf_text(estimate.get('price_updated_at') or 'No verified price date')}", styles['BodyText']),
            Spacer(1, 8),
            Paragraph('Formulas and assumptions', styles['Heading2']),
        ])
        for assumption in estimate.get('assumptions', []):
            story.append(Paragraph('- ' + pdf_text(assumption), styles['BodyText']))
        story.append(Paragraph(
            'Preliminary estimate only. Nominal mix ratios are not design-mix specifications. '
            'Verify local supplier quotations and all structural quantities with qualified professionals.',
            styles['Italic'],
        ))
        pdf.build(story)
        stream.seek(0)
        filename = re.sub(r'[^A-Za-z0-9_-]+', '-', str(record.get('project_name') or 'estimate')).strip('-') or 'estimate'
        return send_file(stream, as_attachment=True, download_name=f'{filename}-material-estimate.pdf',
                         mimetype='application/pdf')
    except (DatabaseUnavailableError, PyMongoError):
        logger.exception('Unable to retrieve material estimate report.')
        return 'Estimation storage is unavailable.', 503


@app.route('/admin/material-prices')
@login_required
@admin_required
def admin_material_prices():
    try:
        prices = _material_price_records()
        locations = _material_location_records()
        catalog = _material_catalog_records()
        settings = _material_estimation_settings()
    except (DatabaseUnavailableError, PyMongoError):
        logger.exception('Unable to load official material prices.')
        return 'Pricing storage is unavailable.', 503
    return render_template(
        'admin_material_prices.html',
        prices=prices,
        locations=locations,
        catalog=catalog,
        settings=settings,
        price_labels=PRICE_LABELS,
        default_mix_ratios=MIX_RATIOS,
        districts=UTTARAKHAND_DISTRICTS,
    )


@app.route('/api/admin/material-prices', methods=['POST'])
@login_required
@admin_required
def admin_save_material_price():
    payload = request.get_json(silent=True)
    try:
        clean = normalize_rate_record(payload, session.get('user_email') or session['user_id'])
        repository = _material_estimation_repository('material_price')
        matches = [
            item for item in repository.list(MATERIAL_PRICE_OWNER, resource_type='material_price')
            if item.get('level') == clean['level']
            and all(
                str(item.get(key) or '').casefold() == str(clean.get(key) or '').casefold()
                for key in ('country', 'state', 'district', 'locality')
            )
        ]
        if matches:
            current = serialize_resource(matches[0])
            clean['rates'] = {**(current.get('rates') or {}), **clean['rates']}
            clean['history'] = list(current.get('history') or []) + [{
                'rates': clean['rates'],
                'source': clean['source'],
                'updated_at': clean['updated_at'],
                'updated_by': clean['updated_by'],
            }]
            updated = repository.update(
                MATERIAL_PRICE_OWNER, current['id'], clean, 'material_price'
            )
        else:
            clean.update({'user_id': MATERIAL_PRICE_OWNER, 'resource_type': 'material_price'})
            updated = repository.create(clean)
        return jsonify({'item': serialize_resource(updated)}), 200
    except EstimationError as exc:
        return jsonify({'error': str(exc)}), 400
    except (DatabaseUnavailableError, PyMongoError):
        logger.exception('Official material price update failed.')
        return jsonify({'error': 'Price storage is unavailable; no rate was changed.'}), 503


@app.route('/api/admin/material-catalog', methods=['POST'])
@login_required
@admin_required
def admin_add_material_catalog_item():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'Material data must be a JSON object.'}), 400
    name = str(payload.get('name') or '').strip()
    unit = str(payload.get('unit') or '').strip()
    if not name or len(name) > 100 or not unit or len(unit) > 40:
        return jsonify({'error': 'Enter a material name (max 100 characters) and unit (max 40 characters).'}), 400
    try:
        repository = _material_estimation_repository('material_catalog')
        existing = repository.list(MATERIAL_PRICE_OWNER, resource_type='material_catalog')
        if any(str(item.get('name') or '').casefold() == name.casefold() for item in existing):
            return jsonify({'error': 'This material is already in the catalogue.'}), 409
        record = repository.create({
            'user_id': MATERIAL_PRICE_OWNER,
            'resource_type': 'material_catalog',
            'name': name,
            'unit': unit,
            'created_by': session.get('user_email') or session['user_id'],
            'updated_at': datetime.utcnow().isoformat(),
        })
        return jsonify({'item': serialize_resource(record)}), 201
    except (DatabaseUnavailableError, PyMongoError):
        logger.exception('Custom material catalogue update failed.')
        return jsonify({'error': 'Material catalogue storage is unavailable; no material was added.'}), 503


@app.route('/api/admin/material-locations', methods=['POST'])
@login_required
@admin_required
def admin_add_material_location():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'Location data must be a JSON object.'}), 400
    level = str(payload.get('level') or '').strip().lower()
    if level not in {'state', 'district', 'locality'}:
        return jsonify({'error': 'Choose state, district, or city/village.'}), 400
    name = str(payload.get('name') or '').strip()
    state = str(payload.get('state') or '').strip()
    district = str(payload.get('district') or '').strip()
    if not name or len(name) > 100 or (level in {'district', 'locality'} and not state) or (level == 'locality' and not district):
        return jsonify({'error': 'Enter the location name and its required parent location.'}), 400
    record = {
        'user_id': MATERIAL_PRICE_OWNER,
        'resource_type': 'material_location',
        'level': level,
        'name': name,
        'country': str(payload.get('country') or 'India').strip()[:80],
        'state': state if level in {'district', 'locality'} else name,
        'district': district if level == 'locality' else (name if level == 'district' else ''),
        'locality': name if level == 'locality' else '',
        'created_by': session.get('user_email') or session['user_id'],
        'updated_at': datetime.utcnow().isoformat(),
    }
    try:
        repository = _material_estimation_repository('material_location')
        exists = any(
            item.get('level') == level
            and all(str(item.get(key) or '').casefold() == str(record.get(key) or '').casefold()
                    for key in ('country', 'state', 'district', 'locality'))
            for item in repository.list(MATERIAL_PRICE_OWNER, resource_type='material_location')
        )
        if exists:
            return jsonify({'error': 'This location is already listed.'}), 409
        created = repository.create(record)
        return jsonify({'item': serialize_resource(created)}), 201
    except (DatabaseUnavailableError, PyMongoError):
        logger.exception('Official location update failed.')
        return jsonify({'error': 'Location storage is unavailable; no location was added.'}), 503


@app.route('/api/admin/material-estimation-settings', methods=['POST'])
@login_required
@admin_required
def admin_save_material_estimation_settings():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'Settings must be a JSON object.'}), 400
    try:
        clean = {}
        for key, minimum, maximum in (
            ('wastage_percent', 0, 100),
            ('dry_volume_factor', 1, 3),
            ('water_cement_ratio', 0.1, 2),
        ):
            value = float(payload.get(key))
            if not math.isfinite(value) or value < minimum or value > maximum:
                raise ValueError(f'{key.replace("_", " ").title()} must be between {minimum:g} and {maximum:g}.')
            clean[key] = value
        ratios = payload.get('mix_ratios')
        if not isinstance(ratios, dict):
            raise ValueError('Provide ratios for M10, M15, and M20.')
        clean_ratios = {}
        for grade in ('M10', 'M15', 'M20'):
            grade_ratios = ratios.get(grade)
            if not isinstance(grade_ratios, dict):
                raise ValueError(f'Provide cement, sand, and aggregate ratios for {grade}.')
            clean_ratios[grade] = {}
            for material in ('cement', 'sand', 'aggregate'):
                value = float(grade_ratios.get(material))
                if not math.isfinite(value) or value <= 0 or value > 100:
                    raise ValueError(f'{grade} {material} ratio must be greater than zero and at most 100.')
                clean_ratios[grade][material] = value
        clean.update({
            'mix_ratios': clean_ratios,
            'resource_type': 'material_config',
            'user_id': MATERIAL_PRICE_OWNER,
            'updated_by': session.get('user_email') or session['user_id'],
            'updated_at': datetime.utcnow().isoformat(),
        })
        repository = _material_estimation_repository('material_config')
        existing = repository.list(MATERIAL_PRICE_OWNER, resource_type='material_config')
        if existing:
            current = serialize_resource(existing[0])
            saved = repository.update(MATERIAL_PRICE_OWNER, current['id'], clean, 'material_config')
        else:
            saved = repository.create(clean)
        return jsonify({'item': serialize_resource(saved)})
    except (TypeError, ValueError) as exc:
        return jsonify({'error': str(exc)}), 400
    except (DatabaseUnavailableError, PyMongoError):
        logger.exception('Material estimation settings update failed.')
        return jsonify({'error': 'Settings storage is unavailable; nothing was changed.'}), 503


@app.route('/cost', methods=['GET', 'POST'])
@login_required
def cost():
    categories = ['Civil work', 'Materials', 'Labour', 'Electrical', 'Plumbing', 'Flooring', 'Painting', 'Doors and windows', 'Other expenses']
    simple_estimate = None
    simple_error = None
    simple_mode = request.method == 'POST' and request.form.get('estimate_type') == 'simple'
    detailed_estimate = request.method == 'POST' and not simple_mode
    area_per_floor = request.form.get('area_per_floor', '')
    floor_count = request.form.get('floor_count', '1')
    rate_per_sqft = request.form.get('rate_per_sqft', '')

    if simple_mode:
        area = safe_float(area_per_floor, None)
        floors = safe_float(floor_count, None)
        rate = safe_float(rate_per_sqft, None)
        quality = request.form.get('quality', 'simple').strip().lower()
        location = request.form.get('location', '').strip()
        city = request.form.get('city', '').strip()
        quality_rates = {'simple': 1500, 'standard': 1800, 'premium': 2300, 'luxury': 3000}
        quality_labels = {'simple': 'Simple', 'standard': 'Standard', 'premium': 'Premium', 'luxury': 'Luxury'}
        if area is None or not 1 <= area <= 1000000:
            simple_error = 'Ghar ka area 1 se 10,00,000 sq ft ke beech likhein.'
        elif floors is None or not floors.is_integer() or not 1 <= floors <= 10:
            simple_error = 'Manzilon ki sankhya 1 se 10 tak poori ginti mein likhein.'
        elif rate is None:
            if request.form.get('quality'):
                rate = quality_rates[quality]
            else:
                simple_error = 'Apne ilaqe ka sahi rate, ₹1 se ₹1,00,00,000 per sq ft ke beech likhein.'
        elif not 1 <= rate <= 10000000:
            simple_error = 'Apne ilaqe ka sahi rate, ₹1 se ₹1,00,00,000 per sq ft ke beech likhein.'
        else:
            total_area = area * floors
            total_cost = round(total_area * rate, 2)
            breakdown = [
                {'name': 'Cement', 'amount': round(total_cost * 0.16, 2)},
                {'name': 'Steel', 'amount': round(total_cost * 0.14, 2)},
                {'name': 'Sand', 'amount': round(total_cost * 0.08, 2)},
                {'name': 'Aggregate', 'amount': round(total_cost * 0.06, 2)},
                {'name': 'Bricks', 'amount': round(total_cost * 0.10, 2)},
                {'name': 'Fittings', 'amount': round(total_cost * 0.15, 2)},
                {'name': 'Finishing', 'amount': round(total_cost * 0.15, 2)},
                {'name': 'Electrical', 'amount': round(total_cost * 0.08, 2)},
                {'name': 'Plumbing', 'amount': round(total_cost * 0.08, 2)},
                {'name': 'Labour', 'amount': round(safe_float(request.form.get('labour_rate'), 400) * total_area, 2)},
            ]
            simple_estimate = {
                'area_per_floor': area,
                'floors': int(floors),
                'rate_per_sqft': rate,
                'total_area': total_area,
                'total_cost': total_cost,
                'quality': quality_labels.get(quality, 'Simple'),
                'location': location or 'Default',
                'city': city,
                'breakdown': breakdown,
                'quantities': [
                    {'name': 'Cement', 'quantity': f"{math.ceil(total_area * 0.40):,.0f} Bags"},
                    {'name': 'Steel', 'quantity': f"{total_area * 0.004:.1f} Tons"},
                    {'name': 'Sand', 'quantity': f"{math.ceil(total_area * 1.80):,.0f} cft"},
                    {'name': 'Aggregate', 'quantity': f"{math.ceil(total_area * 1.35):,.0f} cft"},
                    {'name': 'Bricks', 'quantity': f"{math.ceil(total_area * 15):,.0f} pcs"},
                    {'name': 'Paint', 'quantity': f"{math.ceil(total_area * 0.15):,.0f} L"},
                    {'name': 'Flooring', 'quantity': f"{math.ceil(total_area * 0.70):,.0f} sq ft"},
                ],
            }

    values = {item: safe_float(request.form.get('cost_' + item)) for item in categories} if detailed_estimate else {}
    subtotal = sum(values.values())
    contingency = subtotal * 0.05
    return render_template(
        'cost.html',
        categories=categories,
        values=values,
        subtotal=subtotal,
        contingency=contingency,
        total=subtotal + contingency,
        simple_estimate=simple_estimate,
        simple_error=simple_error,
        detailed_estimate=detailed_estimate,
        area_per_floor=area_per_floor,
        floor_count=floor_count,
        rate_per_sqft=rate_per_sqft,
    )


@app.route('/project-estimate', methods=['GET', 'POST'])
@login_required
def project_estimate():
    estimate = None
    estimate_error = None
    if request.method == 'POST':
        try:
            estimate = calculate_project_estimate(request.form)
        except ValueError as error:
            estimate_error = str(error)
    return render_template(
        'project_estimate.html',
        work_phases=PROJECT_ESTIMATE_PHASES,
        estimate=estimate,
        estimate_error=estimate_error,
    )


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


@app.errorhandler(DatabaseUnavailableError)
def database_unavailable(error):
    logger.error('%s', error)
    return render_template('error.html', code=503, message=str(error)), 503


@app.errorhandler(500)
def server_error(error):
    logger.error(
        'Unhandled application error while serving %s %s.',
        request.method,
        request.path,
        exc_info=(type(error), error, error.__traceback__),
    )
    return render_template('error.html', code=500, message='Something went wrong. Please try again.'), 500


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', '5000')),
        debug=os.getenv('FLASK_DEBUG', '0') == '1',
    )
