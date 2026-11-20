import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app import (
    DatabaseUnavailableError,
    FileProjectStore,
    FileUserStore,
    MongoUserStore,
    SupportAgent,
    SupportConversationStore,
    SupportTicketStore,
    calculate_materials,
    calculate_project_estimate,
    estimate_brickwork,
    estimate_concrete_volume,
    PROJECT_STORE_PATH,
    USER_STORE_PATH,
    app,
    mongo,
)


class MongoConnectionTests(unittest.TestCase):
    def test_requests_do_not_close_the_shared_mongo_client(self):
        client = app.test_client()

        with patch.object(mongo.cx, 'close') as close_client:
            self.assertEqual(client.get('/login').status_code, 200)
            self.assertEqual(client.get('/login').status_code, 200)

        close_client.assert_not_called()

    def test_vercel_entrypoint_uses_the_flask_application(self):
        from api.index import app as vercel_app

        self.assertIs(vercel_app, app)

    def test_vercel_auth_routes_report_missing_mongodb_configuration(self):
        client = app.test_client()
        with patch.dict(os.environ, {'VERCEL': '1'}), patch('app._mongo_available', return_value=False), patch('app.SECRET_KEY_CONFIGURED', True):
            register_response = client.post('/register', data={
                'name': 'Vercel User',
                'email': 'vercel@example.com',
                'phone': '+911234567890',
                'password': 'securepass123',
                'confirm_password': 'securepass123',
            })
            login_response = client.post('/login', data={
                'email': 'vercel@example.com',
                'password': 'securepass123',
            })

        for response in (register_response, login_response):
            with self.subTest(status=response.status_code):
                self.assertEqual(response.status_code, 503)
                self.assertIn(b'MONGO_URI', response.data)

    def test_vercel_auth_routes_explain_missing_session_secret(self):
        client = app.test_client()
        with patch.dict(os.environ, {'VERCEL': '1'}), patch('app.SECRET_KEY_CONFIGURED', False):
            login_page = client.get('/login')
            login_submit = client.post('/login', data={'email': 'user@example.com', 'password': 'password'})

        self.assertEqual(login_page.status_code, 503)
        self.assertEqual(login_submit.status_code, 503)
        self.assertIn(b'SECRET_KEY', login_submit.data)


class MongoUserStoreVerificationTests(unittest.TestCase):
    def test_email_verification_code_round_trip_works_for_mongo_store(self):
        class FakeMongoCollection:
            def __init__(self):
                self.docs = []

            def find_one(self, query):
                for doc in self.docs:
                    matched = True
                    for key, value in query.items():
                        if doc.get(key) != value:
                            matched = False
                            break
                    if matched:
                        return doc
                return None

            def insert_one(self, document):
                self.docs.append(document)
                return type('Result', (), {'inserted_id': document.get('_id')})()

            def update_one(self, query, update):
                doc = self.find_one(query)
                if doc is None:
                    return type('Result', (), {'matched_count': 0, 'modified_count': 0})()
                doc.update(update.get('$set', {}))
                return type('Result', (), {'matched_count': 1, 'modified_count': 1})()

        collection = FakeMongoCollection()
        store = MongoUserStore(collection)
        store.insert_one({
            '_id': 'mongo-user-1',
            'email': 'mongo@example.com',
            'phone': '+919999999999',
            'password_hash': generate_password_hash('secret123'),
            'verification_codes': {},
            'email_verified': False,
            'mobile_verified': False,
        })

        with patch('app.send_email_message', return_value=True):
            code = store.issue_verification_code('mongo@example.com', 'email')

        self.assertTrue(code)
        self.assertTrue(store.verify_verification_code('mongo@example.com', 'email', code))
        self.assertTrue(store.find_by_email('mongo@example.com')['email_verified'])


class FileUserStoreTests(unittest.TestCase):
    def test_login_lookup_is_case_insensitive_for_legacy_records(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / 'users.json'
            store = FileUserStore(path)
            store._write({
                'legacy-key': {
                    '_id': 'legacy-user',
                    'name': 'Legacy User',
                    'email': 'Legacy@Example.com',
                    'password_hash': generate_password_hash('legacy-pass'),
                }
            })

            self.assertIsNotNone(store.verify_password('legacy@example.com', 'legacy-pass'))
            self.assertIsNone(store.verify_password('legacy@example.com', 'wrong-pass'))

    def test_login_lookup_rejects_missing_password_hash(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / 'users.json'
            store = FileUserStore(path)
            store._write({
                'missing@example.com': {
                    '_id': 'missing-user',
                    'name': 'Missing Hash',
                    'email': 'missing@example.com',
                }
            })

            self.assertIsNone(store.verify_password('missing@example.com', 'any-pass'))

    def test_register_and_login(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / 'users.json'
            store = FileUserStore(path)
            password_hash = generate_password_hash('secret123')

            created = store.create_user('Amit', 'amit@example.com', password_hash)
            self.assertEqual(created['email'], 'amit@example.com')
            self.assertEqual(store.find_by_email('amit@example.com')['name'], 'Amit')
            self.assertIsNotNone(store.verify_password('amit@example.com', 'secret123'))
            self.assertIsNone(store.verify_password('amit@example.com', 'wrong-password'))

    def test_reset_token_and_verification_workflow(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / 'users.json'
            store = FileUserStore(path)
            store.create_user('Amit', 'amit@example.com', generate_password_hash('secret123'), phone='+919999999999')

            token = store.create_reset_token('amit@example.com')
            self.assertTrue(token)
            self.assertEqual(store.find_by_email('amit@example.com')['reset_token'], token)
            self.assertTrue(store.verify_reset_token(token))

            user = store.find_by_email('amit@example.com')
            with patch('app.send_email_message', return_value=True):
                code = store.issue_verification_code('amit@example.com', 'email')
            self.assertTrue(code)
            self.assertTrue(store.verify_verification_code('amit@example.com', 'email', code))
            self.assertTrue(store.find_by_email('amit@example.com')['email_verified'])

            with patch('app.send_sms_message', return_value=True):
                phone_code = store.issue_verification_code('amit@example.com', 'mobile')
            self.assertTrue(store.verify_verification_code('amit@example.com', 'mobile', phone_code))
            self.assertTrue(store.find_by_email('amit@example.com')['mobile_verified'])

    def test_login_allows_unverified_users_even_when_providers_are_configured(self):
        client = app.test_client()
        with patch.dict(os.environ, {'SMTP_HOST': 'smtp.example.invalid'}):
            users = FileUserStore(USER_STORE_PATH)
            existing = users.find_by_email('guest@example.com')
            if existing:
                data = users._read()
                data.pop('guest@example.com', None)
                users._write(data)
            users.create_user('Guest User', 'guest@example.com', generate_password_hash('guestpass'), phone='+911234567890', email_verified=False, mobile_verified=False)

            with patch('app.get_user_store', return_value=users):
                response = client.post('/login', data={'email': 'guest@example.com', 'password': 'guestpass'}, follow_redirects=False)
                self.assertEqual(response.status_code, 302)
                self.assertIn('/dashboard', response.headers.get('Location', ''))
                with client.session_transaction() as session:
                    self.assertEqual(session.get('user_email'), 'guest@example.com')

            data = users._read()
            data.pop('guest@example.com', None)
            users._write(data)


class FileProjectStoreTests(unittest.TestCase):
    def test_project_save_and_retrieval(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / 'projects.json'
            store = FileProjectStore(path)
            created = store.insert_one({
                'user_id': 'user-1',
                'project_name': 'Front Villa',
                'plot_length': 30,
                'plot_width': 25,
                'built_up_area': 750,
                'updated_at': __import__('datetime').datetime.utcnow(),
            })

            self.assertEqual(created['project_name'], 'Front Villa')
            recent = store.find_for_user('user-1')
            self.assertTrue(recent)
            self.assertTrue(hasattr(recent[0]['updated_at'], 'strftime'))
            found = store.find_one({'_id': created['_id'], 'user_id': 'user-1'})
            self.assertEqual(found['project_name'], 'Front Villa')


class SupportAgentTests(unittest.TestCase):
    def test_agent_answers_common_customer_question(self):
        knowledge = {
            'faqs': [
                {
                    'keywords': ['three', '3d', 'view'],
                    'answer': 'Use the 3D View button inside the planner to render the model.',
                    'category': 'planner'
                }
            ]
        }
        agent = SupportAgent(knowledge)
        response = agent.answer('3d view not working')
        self.assertIn('3D View', response['answer'])
        self.assertEqual(response['status'], 'matched')

    def test_agent_understands_hindi_and_hinglish_support_questions(self):
        agent = SupportAgent()

        hinglish_response = agent.answer('mera login nahi ho raha')
        self.assertEqual(hinglish_response['status'], 'matched')
        self.assertEqual(hinglish_response['category'], 'account')
        self.assertEqual(hinglish_response['language'], 'hinglish')

        hindi_response = agent.answer('3D मॉडल नहीं दिख रहा')
        self.assertEqual(hindi_response['status'], 'matched')
        self.assertEqual(hindi_response['category'], 'planner')
        self.assertEqual(hindi_response['language'], 'hi')

        fallback_response = agent.answer('मुझे कुछ और मदद चाहिए')
        self.assertEqual(fallback_response['language'], 'hi')
        self.assertIn('मैं', fallback_response['answer'])

    def test_vishwakarma_ai_handles_requested_module_questions(self):
        agent = SupportAgent()
        questions = [
            ('What is Vishwakarma?', 'overview'),
            ('How do I create a house plan?', 'planner'),
            ('How do I use the 3D planner?', 'planner'),
            ('What materials are required for a 1000 sq ft house?', 'materials'),
            ('How is construction cost estimated?', 'cost'),
            ('How does the solar calculator work?', 'solar'),
            ('How does rainwater harvesting calculation work?', 'rainwater'),
            ('What is the Simulation Lab?', 'simulation'),
            ('What is What-if Simulation?', 'simulation'),
            ('How do I save a project?', 'projects'),
            ('How do I generate a report?', 'reports'),
            ('My 3D view is not loading.', 'planner'),
            ('My project is not saving.', 'projects'),
            ('1000 sq ft ghar me cement kitna lagega?', 'materials'),
            ('bhai 2 floor ka ghar banana hai, planner me kaise karu?', 'planner'),
        ]

        for question, category in questions:
            with self.subTest(question=question):
                response = agent.answer(question)
                self.assertIn(response['status'], {'matched', 'knowledge', 'calculated'})
                self.assertEqual(response['category'], category)
                self.assertTrue(response.get('answer'))

    def test_vishwakarma_ai_uses_saved_project_context_for_calculations(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_store = FileProjectStore(Path(tmp_dir) / 'projects.json')
            project_store.insert_one({
                'user_id': 'ai-user',
                'project_name': 'My Home',
                'plot_length': 30,
                'plot_width': 40,
                'unit': 'ft',
                'built_up_area': 1050,
                'floors': 2,
                'rooms': {'Living Room': 1, 'Bedroom': 3},
            })

            with patch('app.get_project_store', return_value=project_store):
                response = SupportAgent().answer('mere ghar ke liye solar kitna lagega?', user_id='ai-user')

            self.assertEqual(response['status'], 'calculated')
            self.assertEqual(response['category'], 'solar')
            self.assertEqual(response['project_context_used'], 'My Home')
            self.assertIn('solar', response['calculator_context'])

    def test_vishwakarma_ai_uses_saved_total_area_once_for_materials(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_store = FileProjectStore(Path(tmp_dir) / 'projects.json')
            project_store.insert_one({
                'user_id': 'ai-user',
                'project_name': 'Two Floor Home',
                'plot_length': 30,
                'plot_width': 40,
                'unit': 'ft',
                'built_up_area': 2000,
                'floors': 2,
            })

            with patch('app.get_project_store', return_value=project_store):
                response = SupportAgent().answer('mere ghar ke liye cement kitna lagega?', user_id='ai-user')

            self.assertEqual(response['calculator_context'], 'calculate_materials')
            self.assertIn('900 50 kg bags', response['answer'])
            self.assertIn('physical units are not defined', response['answer'])

    def test_support_page_and_api_expose_vishwakarma_ai(self):
        client = app.test_client()
        page_response = client.get('/support')
        self.assertEqual(page_response.status_code, 200)
        self.assertIn('Vishwakarma AI', page_response.get_data(as_text=True))

        api_response = client.post('/api/support/ask', json={'question': '1000 sq ft ghar me cement kitna lagega?'})
        self.assertEqual(api_response.status_code, 200)
        payload = api_response.get_json()
        self.assertEqual(payload['status'], 'calculated')
        self.assertEqual(payload['category'], 'materials')
        self.assertEqual(payload['source'], 'calculator')

    def test_health_endpoint_is_available(self):
        client = app.test_client()
        response = client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertIn('status', response.get_json())

    def test_simulation_lab_route_and_material_api(self):
        client = app.test_client()
        route_response = client.get('/simulation')
        self.assertEqual(route_response.status_code, 200)
        self.assertIn('Construction Simulation Lab', route_response.get_data(as_text=True))
        simulation_html = route_response.get_data(as_text=True)
        self.assertIn('Concrete strength is not calculated.', simulation_html)
        self.assertNotIn('name="concrete_grade"', simulation_html)

        api_response = client.post('/api/simulation/material', json={
            'area': 1200,
            'floors': 2,
            'concrete_grade': 'M25',
            'cement_grade': 'OPC 53',
            'steel_grade': 'Fe500',
            'brick_type': 'Fly Ash'
        })
        self.assertEqual(api_response.status_code, 200)
        payload = api_response.get_json()
        self.assertEqual(payload['material_quantities']['cement'], 1080)
        self.assertEqual(payload['factors_per_sq_ft_per_floor']['cement'], 0.45)
        self.assertEqual(payload['material_units']['cement'], '50 kg bag(s)')
        self.assertIn('not IS-code quantities', payload['unit_warning'])
        self.assertNotIn('indicative_strength', payload)
        self.assertNotIn('estimated_material_cost', payload)

    def test_simulation_load_and_cost_are_resilient_to_user_input(self):
        client = app.test_client()

        load_response = client.post('/api/simulation/load', json={
            'load_type': 'Unknown Type',
            'load_value': 60,
        })
        self.assertEqual(load_response.status_code, 200)
        self.assertEqual(load_response.get_json()['load_type'], 'Live Load')

        cost_response = client.post('/api/simulation/cost', json={
            'adjustments': {'cement': 10, 'steel': 10, 'bricks': -5, 'labour': 5}
        })
        self.assertEqual(cost_response.status_code, 200)
        self.assertGreater(cost_response.get_json()['base_cost'], 0)

    def test_cost_calculator_uses_five_percent_contingency(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'user-1'
            session['user_name'] = 'Tester'
            session['user_email'] = 'tester@example.com'

        response = client.post('/cost', data={
            'cost_Civil work': '100000',
            'cost_Materials': '200000',
            'cost_Labour': '50000',
            'cost_Electrical': '-500',
            'cost_Plumbing': '0',
            'cost_Flooring': '25000',
            'cost_Painting': '10000',
            'cost_Doors and windows': '15000',
            'cost_Other expenses': '5000',
        })

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('₹405000', html)
        self.assertIn('₹20250', html)
        self.assertIn('₹425250', html)

    def test_simple_cost_estimate_uses_area_floors_and_local_rate(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'simple-estimate-user'

        response = client.post('/cost', data={
            'estimate_type': 'simple',
            'area_per_floor': '1200',
            'floor_count': '2',
            'rate_per_sqft': '1800',
        })

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('₹4,320,000', html)
        self.assertIn('2 manzil = 2,400 sq ft', html)
        self.assertIn('Mistri ka rate', html)

        invalid_response = client.post('/cost', data={
            'estimate_type': 'simple',
            'area_per_floor': '1200',
            'floor_count': '2',
            'rate_per_sqft': '',
        })
        self.assertIn('Apne ilaqe ka sahi rate', invalid_response.get_data(as_text=True))

    def test_support_persistence_stores_conversation_and_ticket(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            conversation_store = SupportConversationStore(Path(tmp_dir) / 'support-chat.json')
            ticket_store = SupportTicketStore(Path(tmp_dir) / 'support-tickets.json')

            conversation_store.append('session-1', {'role': 'user', 'text': '3d view not working'})
            conversation_store.append('session-1', {'role': 'assistant', 'text': 'Use 3D View button'})

            tickets = ticket_store.log('session-1', {'question': '3d view not working', 'answer': 'Use 3D View button'})

            self.assertEqual(len(conversation_store.load('session-1')), 2)
            self.assertEqual(len(tickets), 1)

    def test_planner_page_exposes_save_form_and_room_inputs(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'user-1'
            session['user_name'] = 'Tester'
            session['user_email'] = 'tester@example.com'

        response = client.get('/planner')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="planner-form"', html)
        self.assertIn('name="project_name"', html)
        self.assertIn('name="plot_length"', html)
        self.assertIn('name="plot_width"', html)
        self.assertIn('name="room_Living Room"', html)
        self.assertIn('data-planner-enhanced', html)
        self.assertIn('id="planner-finish"', html)
        self.assertIn('id="planner-lighting"', html)
        self.assertIn('static/css/planner.css', html)
        self.assertIn('static/js/planner.js', html)
        self.assertIn('id="planner-3d-status"', html)
        self.assertIn('id="architectural-inspector"', html)
        self.assertIn('name="architectural_elements"', html)
        self.assertIn('name="room_height_Bedroom"', html)
        self.assertIn('class="room-remove-tool"', html)
        self.assertIn('aria-label="Remove one Bedroom room"', html)
        self.assertIn('id="cutaway-toggle"', html)
        self.assertIn('id="camera-view"', html)
        self.assertIn('Canopy height', html)
        self.assertIn('id="opening-room-select"', html)
        self.assertIn('id="opening-room-instance"', html)
        self.assertIn('data-opening-kind="ventilator"', html)
        self.assertIn('data-opening-kind="skylight"', html)

    def test_planner_saves_and_reloads_architectural_element_dimensions_positions_and_openings(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'planner-elements-user'
            session['user_name'] = 'Planner User'
            session['user_email'] = 'planner-elements@example.com'

        element = {
            'id': 'bedroom-door',
            'kind': 'door',
            'name': 'Door',
            'room': 'Bedroom',
            'room_index': 0,
            'floor': 0,
            'slot': 0,
            'x': 4.25,
            'y': 9.7,
            'width': 3,
            'depth': 0.3,
            'height': 7,
            'rotation': 0,
        }
        ventilator = {
            'id': 'bedroom-ventilator',
            'kind': 'ventilator',
            'name': 'Ventilator 1',
            'room': 'Bedroom',
            'room_index': 0,
            'floor': 0,
            'slot': 0,
            'x': 8.5,
            'y': 0,
            'width': 2,
            'depth': 0.25,
            'height': 0.8,
            'rotation': 0,
        }
        skylight = {
            'id': 'bedroom-skylight',
            'kind': 'skylight',
            'name': 'Skylight 1',
            'room': 'Bedroom',
            'room_index': 0,
            'floor': 0,
            'slot': 0,
            'x': 4,
            'y': 3,
            'width': 3,
            'depth': 3,
            'height': 0.1,
            'rotation': 0,
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_store = FileProjectStore(Path(tmp_dir) / 'projects.json')
            with patch('app.get_project_store', return_value=project_store):
                response = client.post('/planner', data={
                    'save_project': '1',
                    'project_name': 'Measured Home',
                    'plot_length': '30',
                    'plot_width': '40',
                    'floors': '1',
                    'unit': 'ft',
                    'room_Bedroom': '1',
                    'room_width_Bedroom': '12',
                    'room_depth_Bedroom': '10',
                    'room_height_Bedroom': '9',
                    'layout_data': '{}',
                    'architectural_elements': __import__('json').dumps([element, ventilator, skylight]),
                })
                self.assertEqual(response.status_code, 200)
                saved = project_store.find_for_user('planner-elements-user')[0]
                self.assertEqual(saved['architectural_elements'][0]['x'], 4.25)
                self.assertEqual(saved['architectural_elements'][0]['width'], 3)
                self.assertEqual(saved['architectural_elements'][1]['kind'], 'ventilator')
                self.assertEqual(saved['architectural_elements'][2]['kind'], 'skylight')
                self.assertEqual(saved['room_dimensions']['Bedroom']['height'], 9)
                loaded = client.get(f"/planner?project_id={saved['_id']}")

        self.assertEqual(loaded.status_code, 200)
        self.assertIn(b'bedroom-door', loaded.data)
        self.assertIn(b'bedroom-ventilator', loaded.data)
        self.assertIn(b'bedroom-skylight', loaded.data)
        self.assertIn(b'room_height_Bedroom', loaded.data)

    def test_planner_rejects_architectural_element_outside_room(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'planner-invalid-elements-user'

        element = {
            'id': 'oversized-door',
            'kind': 'door',
            'name': 'Door',
            'room': 'Bedroom',
            'room_index': 0,
            'x': 0,
            'y': 9,
            'width': 13,
            'depth': 0.3,
            'height': 7,
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_store = FileProjectStore(Path(tmp_dir) / 'projects.json')
            with patch('app.get_project_store', return_value=project_store):
                response = client.post('/planner', data={
                    'save_project': '1',
                    'plot_length': '30',
                    'plot_width': '40',
                    'floors': '1',
                    'unit': 'ft',
                    'room_Bedroom': '1',
                    'room_width_Bedroom': '12',
                    'room_depth_Bedroom': '10',
                    'layout_data': '{}',
                    'architectural_elements': __import__('json').dumps([element]),
                })

            self.assertEqual(response.status_code, 200)
            self.assertIn(b'fit the plot', response.data)
            self.assertEqual(project_store.find_for_user('planner-invalid-elements-user'), [])

    def test_materials_and_cost_pages_expose_resource_save_controls(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'ui-user'
            session['user_name'] = 'UI User'
            session['user_email'] = 'ui@example.com'

        materials = client.post('/materials', data={'built_up_area': '1000', 'floors': '2'})
        self.assertEqual(materials.status_code, 200)
        self.assertIn(b'data-resource="materials"', materials.data)
        self.assertIn(b'Factor / sq ft / floor', materials.data)
        self.assertIn(b'50 kg bag', materials.data)
        self.assertIn(b'physical output units are unspecified', materials.data)
        self.assertIn(b'900 50 kg bag(s)', materials.data)
        self.assertIn(b'"unit": "50 kg bag(s)"', materials.data)

        cost = client.post('/cost', data={'cost_Materials': '100000'})
        self.assertEqual(cost.status_code, 200)
        self.assertIn(b'data-resource="expenses"', cost.data)

    def test_material_estimate_uses_total_area_for_planner_project(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'estimate-user'
            session['user_name'] = 'Estimate User'
            session['user_email'] = 'estimate@example.com'

        with tempfile.TemporaryDirectory() as tmp_dir:
            project_store = FileProjectStore(Path(tmp_dir) / 'projects.json')
            with patch('app.get_project_store', return_value=project_store):
                response = client.post('/planner', data={
                    'save_project': '1',
                    'project_name': 'Two Storey Home',
                    'plot_length': '30',
                    'plot_width': '40',
                    'floors': '2',
                    'unit': 'ft',
                    'room_Living Room': '1',
                    'layout_data': '{}',
                })
            self.assertEqual(response.status_code, 200)
            saved = project_store.find_for_user('estimate-user')
            self.assertEqual(saved[0]['material_estimate']['cement'], 756)
            self.assertEqual(saved[0]['material_estimate_units']['cement'], '50 kg bag(s)')
            self.assertIn('not an IS-code quantity takeoff', saved[0]['material_estimate_basis'])

    def test_cement_estimate_rounds_up_by_whole_50_kg_bag(self):
        self.assertEqual(calculate_materials(100, 1)['cement'], 45)
        self.assertEqual(calculate_materials(100, 2)['cement'], 90)
        self.assertEqual(calculate_materials(101, 1)['cement'], 46)

    def test_materials_page_renders_dimension_estimates_and_validation_errors(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'dimensions-user'
            session['user_name'] = 'Dimensions User'
            session['user_email'] = 'dimensions@example.com'

        brickwork_response = client.post('/materials', data={
            'estimate_type': 'brickwork',
            'wall_length_m': '5',
            'wall_height_m': '3',
            'wall_thickness_m': '0.2',
            'openings_area_m2': '2',
            'brick_length_mm': '190',
            'brick_height_mm': '90',
            'brick_width_mm': '90',
            'mortar_joint_mm': '10',
            'cement_ratio': '1',
            'sand_ratio': '6',
            'mortar_dry_factor': '1.33',
            'wastage_percent': '5',
        })
        self.assertEqual(brickwork_response.status_code, 200)
        self.assertIn(b'1365 pieces', brickwork_response.data)
        self.assertIn(b'4 50 kg bags', brickwork_response.data)
        self.assertIn(b'm\xc2\xb3', brickwork_response.data)
        self.assertIn(b'"unit": "pieces"', brickwork_response.data)

        invalid_response = client.post('/materials', data={
            'estimate_type': 'concrete',
            'slab_area_m2': '100',
        })
        self.assertEqual(invalid_response.status_code, 200)
        self.assertIn(b'Enter both slab area and slab thickness', invalid_response.data)

        concrete_response = client.post('/materials', data={
            'estimate_type': 'concrete',
            'slab_area_m2': '100',
            'slab_thickness_mm': '150',
            'column_count': '4',
            'column_width_mm': '300',
            'column_depth_mm': '300',
            'column_height_m': '3',
        })
        self.assertEqual(concrete_response.status_code, 200)
        self.assertIn(b'Total:</b> 16.08 m\xc2\xb3', concrete_response.data)
        self.assertIn(b'"unit": "m\\u00b3 (geometric volume)"', concrete_response.data)

    def test_dimension_based_brickwork_estimates_units_from_wall_measurements(self):
        estimate = estimate_brickwork({
            'wall_length_m': '5',
            'wall_height_m': '3',
            'wall_thickness_m': '0.2',
            'openings_area_m2': '2',
            'brick_length_mm': '190',
            'brick_height_mm': '90',
            'brick_width_mm': '90',
            'mortar_joint_mm': '10',
            'cement_ratio': '1',
            'sand_ratio': '6',
            'mortar_dry_factor': '1.33',
            'wastage_percent': '5',
        })

        self.assertEqual(estimate['net_wall_area_m2'], 13)
        self.assertEqual(estimate['net_masonry_volume_m3'], 2.6)
        self.assertEqual(estimate['bricks_pieces'], 1365)
        self.assertEqual(estimate['cement_bags_50kg'], 4)
        self.assertGreater(estimate['sand_m3'], 0)
        self.assertIn('not an approved mix design', estimate['assumptions'])

    def test_brickwork_rejects_openings_larger_than_wall(self):
        with self.assertRaisesRegex(ValueError, 'Openings area must be less'):
            estimate_brickwork({
                'wall_length_m': '2',
                'wall_height_m': '2',
                'wall_thickness_m': '0.2',
                'openings_area_m2': '4',
                'brick_length_mm': '190',
                'brick_height_mm': '90',
                'brick_width_mm': '90',
                'mortar_joint_mm': '10',
                'cement_ratio': '1',
                'sand_ratio': '6',
                'mortar_dry_factor': '1.33',
                'wastage_percent': '5',
            })

    def test_concrete_dimensions_calculate_volume_without_inferring_mix_or_steel(self):
        estimate = estimate_concrete_volume({
            'slab_area_m2': '100',
            'slab_thickness_mm': '150',
            'column_count': '4',
            'column_width_mm': '300',
            'column_depth_mm': '300',
            'column_height_m': '3',
        })

        self.assertEqual(estimate['components_m3'], {'slab': 15.0, 'columns': 1.08})
        self.assertEqual(estimate['total_m3'], 16.08)
        self.assertIn('No cement, aggregate, or reinforcement', estimate['assumptions'])

    def test_project_estimate_totals_all_phases_and_optional_contingency(self):
        estimate = calculate_project_estimate({
            'qty_excavation': '12',
            'rate_excavation': '500',
            'qty_reinforcement': '300',
            'rate_reinforcement': '70',
            'qty_interior_flooring': '50',
            'rate_interior_flooring': '1200',
            'qty_exterior_paint': '100',
            'rate_exterior_paint': '250',
            'contingency_percent': '5',
        })

        self.assertEqual(estimate['subtotal'], 112000)
        self.assertEqual(estimate['contingency_amount'], 5600)
        self.assertEqual(estimate['grand_total'], 117600)
        non_empty_phases = [phase for phase in estimate['phases'] if phase['items']]
        self.assertEqual(len(non_empty_phases), 4)

    def test_project_estimate_requires_rate_for_entered_quantity(self):
        with self.assertRaisesRegex(ValueError, 'Enter your local unit rate'):
            calculate_project_estimate({'qty_excavation': '12'})
        with self.assertRaisesRegex(ValueError, 'at least one measured quantity'):
            calculate_project_estimate({'contingency_percent': '5'})

    def test_project_estimate_page_shows_work_phases_and_calculated_total(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'project-estimate-user'
            session['user_name'] = 'Project Estimate User'
            session['user_email'] = 'project-estimate@example.com'

        page = client.get('/project-estimate')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Site preparation &amp; foundation', page.data)
        self.assertIn(b'Interior finishing', page.data)
        self.assertIn(b'Exterior finishing &amp; site works', page.data)

        result = client.post('/project-estimate', data={
            'qty_excavation': '12',
            'rate_excavation': '500',
            'qty_reinforcement': '300',
            'rate_reinforcement': '70',
            'contingency_percent': '5',
        })
        self.assertEqual(result.status_code, 200)
        html = result.get_data(as_text=True)
        self.assertIn('₹', html)
        self.assertIn('28,350.00', html)

    def test_planner_can_load_existing_project(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'user-1'
            session['user_name'] = 'Tester'
            session['user_email'] = 'tester@example.com'

        project_store = FileProjectStore(PROJECT_STORE_PATH)
        created = project_store.insert_one({
            'user_id': 'user-1',
            'project_name': 'Villa Plot',
            'plot_length': 32,
            'plot_width': 28,
            'floors': 2,
            'unit': 'ft',
            'built_up_area': 1250,
            'rooms': {'Living Room': 1},
            'room_dimensions': {'Living Room': {'width': 16, 'depth': 12}},
            'updated_at': __import__('datetime').datetime.utcnow()
        })

        try:
            response = client.get(f'/planner?project_id={created["_id"]}')
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertIn('Villa Plot', html)
            self.assertIn('name="plot_length"', html)
        finally:
            project_store.delete_one({'user_id': 'user-1', '_id': created['_id']})

    def test_admin_dashboard_is_protected_and_renders(self):
        client = app.test_client()

        response = client.get('/admin')
        self.assertEqual(response.status_code, 302)

        with client.session_transaction() as session:
            session['user_id'] = 'admin-1'
            session['user_name'] = 'Admin User'
            session['user_email'] = 'admin@example.com'
            session['user_role'] = 'admin'

        response = client.get('/admin')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Admin Dashboard', response.get_data(as_text=True))

    def test_whatsapp_channel_is_supported_for_verification_codes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / 'users.json'
            store = FileUserStore(path)
            store.create_user('Amit', 'amit@example.com', generate_password_hash('secret123'), phone='+919999999999', email_verified=True, mobile_verified=True)

            with patch('app.send_sms_message', return_value=True):
                code = store.issue_verification_code('amit@example.com', 'whatsapp')
                self.assertTrue(code)
                self.assertTrue(store.verify_verification_code('amit@example.com', 'whatsapp', code))
                self.assertTrue(store.find_by_email('amit@example.com')['mobile_verified'])

    def test_register_does_not_require_or_send_an_otp(self):
        client = app.test_client()
        with tempfile.TemporaryDirectory() as tmp_dir:
            users = FileUserStore(Path(tmp_dir) / 'users.json')
            with patch('app.get_user_store', return_value=users), \
                    patch.dict(os.environ, {'SMTP_HOST': 'smtp.example.invalid'}), \
                    patch('app.send_email_message') as send_email, \
                    patch('app.send_sms_message') as send_sms:
                response = client.post('/register', data={
                    'name': 'OTP-free User',
                    'email': 'otp-free@example.com',
                    'phone': '+911234567890',
                    'password': 'securepass123',
                    'confirm_password': 'securepass123',
                })

            self.assertEqual(response.status_code, 302)
            self.assertIn('/dashboard', response.headers.get('Location', ''))
            account = users.find_by_email('otp-free@example.com')
            self.assertTrue(account['email_verified'])
            self.assertTrue(account['mobile_verified'])
            send_email.assert_not_called()
            send_sms.assert_not_called()

    def test_verify_account_link_redirects_without_requesting_a_code(self):
        client = app.test_client()
        response = client.get('/verify_account')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers.get('Location', ''))

        with client.session_transaction() as session:
            session['user_id'] = 'user-1'
        response = client.get('/verify_account')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/dashboard', response.headers.get('Location', ''))

    def test_project_milestones_can_be_added(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'user-1'
            session['user_name'] = 'Tester'
            session['user_email'] = 'tester@example.com'

        project_store = FileProjectStore(PROJECT_STORE_PATH)
        created = project_store.insert_one({
            'user_id': 'user-1',
            'project_name': 'Milestone Home',
            'plot_length': 30,
            'plot_width': 25,
            'floors': 2,
            'unit': 'ft',
            'built_up_area': 900,
            'updated_at': __import__('datetime').datetime.utcnow()
        })

        try:
            with patch('app.get_project_store', return_value=project_store):
                response = client.post(f"/project/{created['_id']}/milestones", data={
                    'title': 'Foundation work',
                    'status': 'in_progress',
                    'due_date': '2026-10-15',
                    'notes': 'Excavate and pour raft footing.'
                }, follow_redirects=False)
            self.assertIn(response.status_code, {200, 302})

            project = project_store.find_one({'user_id': 'user-1', '_id': created['_id']})
            self.assertTrue(project.get('milestones'))
            self.assertEqual(project['milestones'][0]['title'], 'Foundation work')
            self.assertEqual(project['milestones'][0]['status'], 'in_progress')
        finally:
            project_store.delete_one({'user_id': 'user-1', '_id': created['_id']})

    def test_design_alternatives_can_be_compared_for_cost(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'user-1'
            session['user_name'] = 'Tester'
            session['user_email'] = 'tester@example.com'

        project_store = FileProjectStore(PROJECT_STORE_PATH)
        created = project_store.insert_one({
            'user_id': 'user-1',
            'project_name': 'Alternative Home',
            'plot_length': 30,
            'plot_width': 25,
            'floors': 2,
            'unit': 'ft',
            'built_up_area': 900,
            'updated_at': __import__('datetime').datetime.utcnow()
        })

        try:
            with patch('app.get_project_store', return_value=project_store):
                response = client.post(f"/project/{created['_id']}/alternatives", data={
                    'name': 'Option A',
                    'description': 'Compact 2BHK',
                    'built_up_area': '950',
                    'materials_cost': '1800000',
                    'labour_cost': '900000',
                    'other_cost': '250000',
                    'status': 'recommended'
                }, follow_redirects=False)
                self.assertIn(response.status_code, {200, 302})

                page_response = client.get(f"/project/{created['_id']}/alternatives")
            self.assertEqual(page_response.status_code, 200)
            self.assertIn('Recommended', page_response.get_data(as_text=True))

            with patch('app.get_project_store', return_value=project_store):
                export_response = client.get(f"/project/{created['_id']}/alternatives.xlsx")
            self.assertEqual(export_response.status_code, 200)
            self.assertIn('xlsx', export_response.headers.get('Content-Disposition', '').lower())

            project = project_store.find_one({'user_id': 'user-1', '_id': created['_id']})
            self.assertTrue(project.get('design_alternatives'))
            self.assertEqual(project['design_alternatives'][0]['name'], 'Option A')
            self.assertEqual(project['design_alternatives'][0]['total_cost'], 2950000)
        finally:
            project_store.delete_one({'user_id': 'user-1', '_id': created['_id']})

    def test_construction_resource_apis_support_crud_and_validation(self):
        client = app.test_client()
        resource_user_id = f'resource-user-{uuid.uuid4().hex}'
        with client.session_transaction() as session:
            session['user_id'] = resource_user_id
            session['user_name'] = 'Resource User'
            session['user_email'] = 'resource@example.com'

        payloads = {
            'labour': {'name': 'Mason', 'role': 'Mason', 'rate': 850},
            'materials': {'name': 'Cement', 'unit': 'bag', 'unit_cost': 420},
            'equipment': {'name': 'Mixer', 'rate': 1200},
            'tasks': {'title': 'Foundation inspection'},
            'expenses': {'description': 'Site transport', 'amount': 2500},
            'documents': {'name': 'Soil report', 'document_type': 'report'},
            'invoices': {'invoice_number': 'INV-001', 'vendor': 'Supplier', 'amount': 15000},
        }
        created_ids = {}
        for resource_type, payload in payloads.items():
            with self.subTest(resource_type=resource_type):
                response = client.post(f'/api/{resource_type}', json=payload)
                self.assertEqual(response.status_code, 201)
                created_ids[resource_type] = response.get_json()['item']['id']

                listing = client.get(f'/api/{resource_type}')
                self.assertEqual(listing.status_code, 200)
                self.assertEqual(listing.get_json()['count'], 1)

                updated = client.patch(f'/api/{resource_type}/{created_ids[resource_type]}', json=payload)
                self.assertEqual(updated.status_code, 200)

        invalid = client.post('/api/expenses', json={'description': 'Missing amount'})
        self.assertEqual(invalid.status_code, 400)

        with client.session_transaction() as session:
            session['user_id'] = 'other-user'
        hidden = client.get(f"/api/tasks/{created_ids['tasks']}")
        self.assertEqual(hidden.status_code, 404)


if __name__ == '__main__':
    unittest.main()
