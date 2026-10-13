import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app import FileProjectStore, FileUserStore, SupportAgent, SupportConversationStore, SupportTicketStore, PROJECT_STORE_PATH, USER_STORE_PATH, app


class FileUserStoreTests(unittest.TestCase):
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

    def test_login_allows_unverified_users_when_no_provider_is_configured(self):
        client = app.test_client()
        with patch.dict(os.environ, {
            'SMTP_HOST': '',
            'SMTP_USERNAME': '',
            'MAIL_USERNAME': '',
            'TWILIO_ACCOUNT_SID': '',
            'SENDGRID_API_KEY': '',
            'FIREBASE_PROJECT_ID': '',
        }, clear=False):
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

        api_response = client.post('/api/simulation/material', json={
            'area': 1200,
            'floors': 2,
            'concrete_grade': 'M25',
            'cement_grade': 'OPC 53',
            'steel_grade': 'Fe500',
            'brick_type': 'Fly Ash'
        })
        self.assertEqual(api_response.status_code, 200)
        self.assertIn('indicative_strength', api_response.get_json())

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

    def test_materials_and_cost_pages_expose_resource_save_controls(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'ui-user'
            session['user_name'] = 'UI User'
            session['user_email'] = 'ui@example.com'

        materials = client.post('/materials', data={'built_up_area': '1000', 'floors': '1'})
        self.assertEqual(materials.status_code, 200)
        self.assertIn(b'data-resource="materials"', materials.data)

        cost = client.post('/cost', data={'cost_Materials': '100000'})
        self.assertEqual(cost.status_code, 200)
        self.assertIn(b'data-resource="expenses"', cost.data)

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

    def test_verify_account_page_lists_whatsapp_option(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'user-1'
            session['user_name'] = 'Tester'
            session['user_email'] = 'tester@example.com'

        response = client.get('/verify_account')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('value="whatsapp"', html)

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
