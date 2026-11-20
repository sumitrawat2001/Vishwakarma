import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import FileProjectStore, app
from construction_modules import FileResourceRepository
from vastu_engine import analyze_rule_sets, analyze_vastu, directions_from_layout
from vastu_consultant import answer_vastu_question


class VastuEngineTests(unittest.TestCase):
    def test_weighted_score_uses_only_valid_user_directions(self):
        result = analyze_vastu(
            30,
            40,
            'rectangular',
            'N',
            {'main_entrance': 'N', 'kitchen': 'SW'},
            {'main_entrance': 'N', 'kitchen': 'SE'},
        )

        self.assertEqual(result['score'], 60)
        self.assertEqual(result['matched_count'], 1)
        self.assertEqual(result['needs_review_count'], 1)
        self.assertEqual(result['missing_count'], 7)
        self.assertEqual(result['assessed_weight'], 2.5)
        self.assertEqual(result['total_weight'], 9.5)

    def test_missing_directions_have_no_score(self):
        result = analyze_vastu(30, 40, 'rectangular', 'N', {})

        self.assertIsNone(result['score'])
        self.assertEqual(result['coverage_percent'], 0)
        self.assertEqual(result['missing_count'], 9)

    def test_layout_positions_follow_selected_plan_north(self):
        layout = {'Kitchen': [{'x': 650, 'y': 100}]}

        self.assertEqual(directions_from_layout(layout, 'N')['kitchen'], 'NE')
        self.assertEqual(directions_from_layout(layout, 'E')['kitchen'], 'SE')

    def test_square_plots_require_equal_dimensions(self):
        with self.assertRaisesRegex(ValueError, 'length and width must be equal'):
            analyze_vastu(30, 40, 'square', 'N', {})

    def test_custom_rule_weight_changes_score_deterministically(self):
        result = analyze_vastu(
            30,
            40,
            'rectangular',
            'N',
            {'main_entrance': 'N', 'kitchen': 'SW'},
            {'main_entrance': 'N', 'kitchen': 'SE'},
            {'main_entrance': 1, 'kitchen': 3},
        )

        self.assertEqual(result['score'], 25)
        self.assertEqual(result['assessed_weight'], 4)

    def test_rule_sets_classify_match_partial_difference_and_missing_data(self):
        result = analyze_rule_sets(
            {'kitchen': 'SE', 'master_bedroom': 'N'},
            [{
                'id': 'custom-entry',
                'rule_name': 'Family kitchen',
                'component': 'kitchen',
                'preferred_directions': ['NE'],
                'alternative_directions': ['SE'],
                'priority': 'high',
                'enabled': True,
            }],
            'combined',
        )

        custom = next(rule for rule in result['rules'] if rule['rule_id'] == 'custom-entry')
        standard_kitchen = next(rule for rule in result['rules'] if rule['rule_id'] == 'standard:kitchen')
        standard_entrance = next(rule for rule in result['rules'] if rule['rule_id'] == 'standard:main_entrance')
        standard_bedroom = next(rule for rule in result['rules'] if rule['rule_id'] == 'standard:master_bedroom')
        self.assertEqual(custom['status'], 'partial')
        self.assertEqual(standard_kitchen['status'], 'matches')
        self.assertEqual(standard_bedroom['status'], 'differs')
        self.assertEqual(standard_entrance['status'], 'insufficient')
        self.assertTrue(custom['conflict'])
        self.assertTrue(standard_kitchen['conflict'])
        self.assertEqual(len(result['conflicts']), 1)


class VastuConsultantTests(unittest.TestCase):
    def test_answers_follow_configured_rules_in_english_and_hindi(self):
        rules = [{
            'component': 'kitchen',
            'preferred_direction': 'E',
            'preferred_directions': ['E'],
            'alternative_directions': ['NE'],
            'enabled': True,
        }]

        english = answer_vastu_question('Which direction is best for the kitchen?', rules)
        hindi = answer_vastu_question('रसोई किस दिशा में होनी चाहिए?', rules)

        self.assertIn('East (E)', english)
        self.assertIn('पूर्व (E)', hindi)
        self.assertNotIn('Southeast (SE)', english)

    def test_disabled_or_empty_rule_set_is_not_replaced_by_defaults(self):
        answer = answer_vastu_question('Kitchen direction?', [])

        self.assertIn('no active configured rule', answer.lower())
        self.assertNotIn('Southeast', answer)


class VastuRouteTests(unittest.TestCase):
    def test_vastu_page_renders_optional_local_helper_without_ai_service(self):
        client = app.test_client()
        with tempfile.TemporaryDirectory() as tmp_dir:
            projects = FileProjectStore(Path(tmp_dir) / 'projects.json')
            resources = FileResourceRepository(Path(tmp_dir) / 'resources.json')
            with client.session_transaction() as session:
                session['user_id'] = 'vastu-helper-user'
            with patch('app.get_project_store', return_value=projects), patch('app.get_resource_repository', return_value=resources):
                response = client.get('/vastu')

        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Chat with your Vastu Consultant', page)
        self.assertIn('Previous consultations', page)
        self.assertIn('Rule-based', page)
        self.assertIn('vastu-helper-context', page)
        self.assertIn('ko analysis ke liye OpenAI ko bhejne ki meri sahmati hai', page)
        self.assertIn('static/js/vastu-helper.js', page)

    def test_consultations_are_saved_and_private_to_each_user(self):
        owner = app.test_client()
        other = app.test_client()
        with tempfile.TemporaryDirectory() as tmp_dir:
            projects = FileProjectStore(Path(tmp_dir) / 'projects.json')
            resources = FileResourceRepository(Path(tmp_dir) / 'resources.json')
            with owner.session_transaction() as session:
                session['user_id'] = 'consultation-owner'
            with other.session_transaction() as session:
                session['user_id'] = 'other-consultation-user'

            with patch('app.get_resource_repository', return_value=resources), patch('app.get_project_store', return_value=projects):
                first = owner.post('/api/vastu/chat', json={'question': 'Kitchen direction?'})
                self.assertEqual(first.status_code, 200)
                self.assertIn('Southeast (SE)', first.json['answer'])
                consultation_id = first.json['consultation_id']
                second = owner.post('/api/vastu/chat', json={
                    'question': 'Where should I construct my bedroom?',
                    'consultation_id': consultation_id,
                })
                self.assertEqual(second.status_code, 200)
                self.assertEqual(len(second.json['messages']), 4)
                self.assertEqual(owner.get('/api/vastu/consultations').json['count'], 1)
                self.assertEqual(other.get('/api/vastu/consultations').json['count'], 0)
                self.assertEqual(other.get(f'/api/vastu/consultations/{consultation_id}').status_code, 404)

    def test_chat_rejects_empty_or_oversized_questions(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'invalid-question-user'

        self.assertEqual(client.post('/api/vastu/chat', json={'question': '  '}).status_code, 400)
        self.assertEqual(client.post('/api/vastu/chat', json={'question': 'x' * 501}).status_code, 400)

    def test_floor_plan_requires_consent_and_openai_configuration(self):
        client = app.test_client()
        png = b'\x89PNG\r\n\x1a\n' + b'test image bytes'
        with tempfile.TemporaryDirectory() as tmp_dir:
            resources = FileResourceRepository(Path(tmp_dir) / 'resources.json')
            with client.session_transaction() as session:
                session['user_id'] = 'floor-plan-user'
            with patch('app.get_resource_repository', return_value=resources), patch.dict('os.environ', {'OPENAI_API_KEY': ''}), patch('app._call_llm') as llm:
                no_consent = client.post('/api/vastu/chat', data={
                    'question': 'Please inspect this floor plan',
                    'floor_plan': (io.BytesIO(png), 'plan.png', 'image/png'),
                })
                self.assertEqual(no_consent.status_code, 400)
                not_configured = client.post('/api/vastu/chat', data={
                    'question': 'Please inspect this floor plan',
                    'openai_consent': 'true',
                    'floor_plan': (io.BytesIO(png), 'plan.png', 'image/png'),
                })
                self.assertEqual(not_configured.status_code, 503)
                self.assertEqual(resources.list('floor-plan-user', resource_type='vastu_consultations'), [])
                self.assertEqual(resources.list('floor-plan-user', resource_type='vastu_consultation_images'), [])
                llm.assert_not_called()

    def test_floor_plan_is_sent_to_vision_and_saved_privately_with_consultation(self):
        owner = app.test_client()
        other = app.test_client()
        png = b'\x89PNG\r\n\x1a\n' + b'test image bytes'
        with tempfile.TemporaryDirectory() as tmp_dir:
            resources = FileResourceRepository(Path(tmp_dir) / 'resources.json')
            with owner.session_transaction() as session:
                session['user_id'] = 'vision-image-owner'
            with other.session_transaction() as session:
                session['user_id'] = 'other-vision-user'
            with patch('app.get_resource_repository', return_value=resources), patch.dict('os.environ', {'OPENAI_API_KEY': 'unit-test-key'}), patch('app._call_llm', return_value='The image appears to show labeled rooms. Confirm the north direction before applying Vastu rules.') as llm:
                response = owner.post('/api/vastu/chat', data={
                    'question': 'Can you review my floor plan?',
                    'openai_consent': 'true',
                    'floor_plan': (io.BytesIO(png), 'my-plan.png', 'image/png'),
                })
                self.assertEqual(response.status_code, 200)
                consultation_id = response.json['consultation_id']
                attachment_id = response.json['attachment']['id']
                self.assertTrue(llm.called)
                sent_image = llm.call_args.args[0][1]['content'][1]['image_url']['url']
                self.assertTrue(sent_image.startswith('data:image/png;base64,'))
                consultation = owner.get(f'/api/vastu/consultations/{consultation_id}')
                self.assertEqual(consultation.status_code, 200)
                self.assertEqual(consultation.json['item']['messages'][-2]['attachments'][0]['id'], attachment_id)
                saved_image = owner.get(
                    f'/api/vastu/consultations/{consultation_id}/images/{attachment_id}'
                )
                self.assertEqual(saved_image.status_code, 200)
                self.assertEqual(saved_image.mimetype, 'image/png')
                self.assertEqual(saved_image.data, png)
                self.assertEqual(saved_image.headers['Cache-Control'], 'private, no-store')
                self.assertEqual(saved_image.headers['X-Content-Type-Options'], 'nosniff')

                follow_up = owner.post('/api/vastu/chat', data={
                    'question': 'Can you also check this updated plan?',
                    'consultation_id': consultation_id,
                    'openai_consent': 'true',
                    'floor_plan': (io.BytesIO(png), 'updated-plan.png', 'image/png'),
                })
                self.assertEqual(follow_up.status_code, 200)
                follow_up_attachment_id = follow_up.json['attachment']['id']
                updated_consultation = owner.get(f'/api/vastu/consultations/{consultation_id}')
                self.assertEqual(
                    updated_consultation.json['item']['messages'][-2]['attachments'][0]['id'],
                    follow_up_attachment_id,
                )
                self.assertEqual(
                    owner.get(
                        f'/api/vastu/consultations/{consultation_id}/images/{follow_up_attachment_id}'
                    ).data,
                    png,
                )
                self.assertEqual(
                    other.get(f'/api/vastu/consultations/{consultation_id}/images/{attachment_id}').status_code,
                    404,
                )

    def test_admin_rules_are_configurable_and_drive_standard_analysis(self):
        client = app.test_client()
        with tempfile.TemporaryDirectory() as tmp_dir:
            projects = FileProjectStore(Path(tmp_dir) / 'projects.json')
            resources = FileResourceRepository(Path(tmp_dir) / 'resources.json')
            with client.session_transaction() as session:
                session['user_id'] = 'vastu-admin'
                session['user_role'] = 'admin'

            with patch('app.get_resource_repository', return_value=resources), patch('app.get_project_store', return_value=projects):
                initialized = client.get('/api/admin/vastu/rules')
                self.assertEqual(initialized.status_code, 200)
                kitchen = next(item for item in initialized.json['items'] if item['component'] == 'kitchen')
                management_page = client.get('/admin/vastu-rules')
                self.assertEqual(management_page.status_code, 200)
                self.assertIn('Manage Vastu rules', management_page.get_data(as_text=True))
                self.assertEqual(client.patch(
                    f"/api/admin/vastu/rules/{kitchen['id']}",
                    data='[]',
                    content_type='application/json',
                ).status_code, 400)
                updated = client.patch(f"/api/admin/vastu/rules/{kitchen['id']}", json={
                    'preferred_direction': 'E',
                })
                self.assertEqual(updated.status_code, 200)
                self.assertEqual(updated.json['item']['preferred_direction'], 'E')
                created = client.post('/api/admin/vastu/rules', json={
                    'rule_name': 'Shared living-room preference',
                    'component': 'living_room',
                    'preferred_direction': 'E',
                    'alternative_directions': ['NE'],
                    'priority': 'high',
                    'enabled': False,
                })
                self.assertEqual(created.status_code, 201)
                self.assertFalse(created.json['item']['enabled'])
                self.assertEqual(
                    client.delete(f"/api/admin/vastu/rules/{created.json['item']['id']}").status_code,
                    204,
                )
                analyzed = client.post('/vastu', data={
                    'project_name': 'Admin Rule Home',
                    'plot_length': '30',
                    'plot_width': '40',
                    'unit': 'ft',
                    'plot_shape': 'rectangular',
                    'north_direction': 'N',
                    'direction_kitchen': 'E',
                }, follow_redirects=True)
                saved = projects.find_for_user('vastu-admin')[0]
                kitchen_result = next(
                    rule for rule in saved['vastu_analysis']['analysis_details']['rules']
                    if rule['component'] == 'kitchen'
                )

        self.assertEqual(analyzed.status_code, 200)
        self.assertEqual(kitchen_result['preferred_directions'], ['E'])
        self.assertEqual(kitchen_result['category'], 'Admin configured')

    def test_non_admin_cannot_manage_shared_vastu_rules(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'regular-vastu-user'
            session['user_role'] = 'user'

        self.assertEqual(client.get('/admin/vastu-rules').status_code, 302)
        self.assertEqual(client.post('/api/admin/vastu/rules', json={}).status_code, 302)

    def test_analysis_is_saved_and_report_downloads(self):
        client = app.test_client()
        with tempfile.TemporaryDirectory() as tmp_dir:
            projects = FileProjectStore(Path(tmp_dir) / 'projects.json')
            with client.session_transaction() as session:
                session['user_id'] = 'vastu-user'
                session['user_name'] = 'Vastu User'
                session['user_email'] = 'vastu@example.com'

            form = {
                'project_name': 'Courtyard Home',
                'plot_length': '30',
                'plot_width': '40',
                'unit': 'ft',
                'plot_shape': 'rectangular',
                'north_direction': 'N',
                'direction_main_entrance': 'N',
                'direction_kitchen': 'SE',
                'direction_master_bedroom': 'SW',
                'direction_living_room': 'NE',
                'direction_pooja_room': 'NE',
                'direction_bathroom_toilet': 'NW',
                'direction_staircase': 'S',
                'direction_overhead_water_tank': 'SW',
                'direction_underground_water_source': 'NE',
            }
            with patch('app.get_project_store', return_value=projects):
                response = client.post('/vastu', data=form, follow_redirects=True)
                self.assertEqual(response.status_code, 200)
                self.assertIn('Vastu analysis saved to your project.', response.get_data(as_text=True))
                saved = projects.find_for_user('vastu-user')[0]
                self.assertEqual(saved['vastu_analysis']['score'], 100)
                report = client.get(f"/vastu/{saved['_id']}/report.pdf")

            self.assertEqual(report.status_code, 200)
            self.assertEqual(report.mimetype, 'application/pdf')
            self.assertTrue(report.data.startswith(b'%PDF'))

    def test_vastu_page_requires_authentication(self):
        response = app.test_client().get('/vastu')

        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.headers.get('Location', ''))

    def test_custom_rules_are_crud_validated_and_user_scoped(self):
        first_client = app.test_client()
        second_client = app.test_client()
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = FileResourceRepository(Path(tmp_dir) / 'resources.json')
            with first_client.session_transaction() as session:
                session['user_id'] = 'vastu-rule-owner'
            with second_client.session_transaction() as session:
                session['user_id'] = 'other-vastu-user'
            with patch('app.get_resource_repository', return_value=repository):
                created = first_client.post('/api/vastu/rules', json={
                    'rule_name': 'Family kitchen',
                    'component': 'kitchen',
                    'preferred_direction': 'E',
                    'alternative_directions': ['NE', 'E', 'INVALID'],
                    'priority': 'high',
                })
                self.assertEqual(created.status_code, 400)
                created = first_client.post('/api/vastu/rules', json={
                    'rule_name': 'Family kitchen',
                    'component': 'kitchen',
                    'preferred_direction': 'E',
                    'alternative_directions': ['NE', 'E'],
                    'priority': 'high',
                })
                self.assertEqual(created.status_code, 201)
                rule_id = created.json['item']['id']
                self.assertEqual(created.json['item']['alternative_directions'], ['NE'])
                self.assertEqual(second_client.get('/api/vastu/rules').json['count'], 0)
                self.assertEqual(second_client.patch(f'/api/vastu/rules/{rule_id}', json={'enabled': False}).status_code, 404)
                updated = first_client.patch(f'/api/vastu/rules/{rule_id}', json={'enabled': False})
                self.assertEqual(updated.status_code, 200)
                self.assertFalse(updated.json['item']['enabled'])
                self.assertEqual(first_client.get(f'/api/vastu/rules/{rule_id}').json['item']['rule_name'], 'Family kitchen')
                self.assertEqual(first_client.delete(f'/api/vastu/rules/{rule_id}').status_code, 204)
                self.assertEqual(first_client.get('/api/vastu/rules').json['count'], 0)

    def test_custom_analysis_mode_uses_saved_user_rules(self):
        client = app.test_client()
        with tempfile.TemporaryDirectory() as tmp_dir:
            projects = FileProjectStore(Path(tmp_dir) / 'projects.json')
            resources = FileResourceRepository(Path(tmp_dir) / 'resources.json')
            with client.session_transaction() as session:
                session['user_id'] = 'custom-analysis-user'
            resources.create({
                'user_id': 'custom-analysis-user',
                'resource_type': 'vastu_rules',
                'rule_name': 'Family kitchen',
                'component': 'kitchen',
                'preferred_direction': 'SE',
                'preferred_directions': ['SE'],
                'alternative_directions': ['E'],
                'priority': 'high',
                'enabled': True,
                'weight': 3,
            })
            with patch('app.get_project_store', return_value=projects), patch('app.get_resource_repository', return_value=resources):
                response = client.post('/vastu', data={
                    'project_name': 'Custom Home',
                    'plot_length': '30',
                    'plot_width': '40',
                    'unit': 'ft',
                    'plot_shape': 'rectangular',
                    'north_direction': 'N',
                    'analysis_mode': 'custom',
                    'direction_kitchen': 'SE',
                }, follow_redirects=True)
                saved = projects.find_for_user('custom-analysis-user')[0]

        self.assertEqual(response.status_code, 200)
        details = saved['vastu_analysis']['analysis_details']
        self.assertEqual(details['mode'], 'custom')
        self.assertEqual(details['matches'], 1)
        self.assertEqual(details['insufficient'], 0)
        self.assertEqual(details['score'], 100)
        self.assertIn('Family kitchen', response.get_data(as_text=True))

    def test_saved_reports_can_be_reopened_deleted_and_are_private(self):
        owner_client = app.test_client()
        other_client = app.test_client()
        with tempfile.TemporaryDirectory() as tmp_dir:
            projects = FileProjectStore(Path(tmp_dir) / 'projects.json')
            resources = FileResourceRepository(Path(tmp_dir) / 'resources.json')
            project = projects.insert_one({
                'user_id': 'report-owner',
                'project_name': 'Report Home',
                'plot_length': 30,
                'plot_width': 40,
                'unit': 'ft',
                'vastu_settings': {'analysis_mode': 'standard'},
                'vastu_analysis': analyze_vastu(
                    30, 40, 'rectangular', 'N', {'kitchen': 'SE'}
                ),
            })
            with owner_client.session_transaction() as session:
                session['user_id'] = 'report-owner'
            with other_client.session_transaction() as session:
                session['user_id'] = 'not-report-owner'
            with patch('app.get_project_store', return_value=projects), patch('app.get_resource_repository', return_value=resources):
                saved = owner_client.post('/api/vastu/reports', json={'project_id': project['_id']})
                self.assertEqual(saved.status_code, 201)
                report_id = saved.json['item']['id']
                self.assertEqual(other_client.get('/api/vastu/reports').json['count'], 0)
                self.assertEqual(other_client.delete(f'/api/vastu/reports/{report_id}').status_code, 404)
                reopened = owner_client.get(f'/vastu?report_id={report_id}')
                self.assertEqual(reopened.status_code, 200)
                self.assertIn('Saved snapshot', reopened.get_data(as_text=True))
                saved_pdf = owner_client.get(f'/vastu/reports/{report_id}.pdf')
                self.assertEqual(saved_pdf.status_code, 200)
                self.assertEqual(saved_pdf.mimetype, 'application/pdf')
                self.assertTrue(saved_pdf.data.startswith(b'%PDF'))
                self.assertEqual(owner_client.delete(f'/api/vastu/reports/{report_id}').status_code, 204)
                self.assertEqual(owner_client.get('/api/vastu/reports').json['count'], 0)

    def test_existing_project_layout_is_used_for_room_direction(self):
        client = app.test_client()
        with tempfile.TemporaryDirectory() as tmp_dir:
            projects = FileProjectStore(Path(tmp_dir) / 'projects.json')
            saved = projects.insert_one({
                'user_id': 'vastu-user',
                'project_name': 'Layout Home',
                'plot_length': 30,
                'plot_width': 40,
                'unit': 'ft',
                'layout_data': {'Kitchen': [{'x': 650, 'y': 100}]},
            })
            with client.session_transaction() as session:
                session['user_id'] = 'vastu-user'
            with patch('app.get_project_store', return_value=projects):
                response = client.get(f"/vastu?project_id={saved['_id']}")
                self.assertEqual(response.status_code, 200)
                analyzed = client.post('/vastu', data={
                    'project_id': saved['_id'],
                    'north_direction': 'N',
                    'direction_kitchen': 'S',
                    'guideline_kitchen': 'NE',
                }, follow_redirects=True)
                updated = projects.find_one({'user_id': 'vastu-user', '_id': saved['_id']})

        self.assertEqual(response.status_code, 200)
        self.assertIn('From saved 2D layout · Northeast', response.get_data(as_text=True))
        self.assertEqual(analyzed.status_code, 200)
        kitchen = next(rule for rule in updated['vastu_analysis']['rules'] if rule['key'] == 'kitchen')
        self.assertEqual(kitchen['selected_direction'], 'NE')
        self.assertEqual(kitchen['source'], 'planner layout')
        self.assertEqual(kitchen['status'], 'matched')

    def test_planner_saves_draggable_room_positions(self):
        client = app.test_client()
        with tempfile.TemporaryDirectory() as tmp_dir:
            projects = FileProjectStore(Path(tmp_dir) / 'projects.json')
            with client.session_transaction() as session:
                session['user_id'] = 'vastu-user'
                session['user_name'] = 'Vastu User'
                session['user_email'] = 'vastu@example.com'

            with patch('app.get_project_store', return_value=projects):
                response = client.post('/planner', data={
                    'save_project': '1',
                    'project_name': 'Positioned Home',
                    'plot_length': '30',
                    'plot_width': '40',
                    'floors': '1',
                    'unit': 'ft',
                    'room_Kitchen': '1',
                    'layout_data': '{"Kitchen":[{"x":650,"y":100}]}',
                })

            self.assertEqual(response.status_code, 200)
            saved = projects.find_for_user('vastu-user')[0]
            self.assertEqual(saved['layout_data']['Kitchen'], [{'x': 650.0, 'y': 100.0}])


if __name__ == '__main__':
    unittest.main()
