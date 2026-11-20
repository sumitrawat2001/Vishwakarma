import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import FileProjectStore, app


class StructuralDesignStudioTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        self.project_path = self.directory / 'projects.json'
        self.resource_path = self.directory / 'resources.json'
        self.user_id = 'structural-user'
        self.project_id = 'structural-project'
        FileProjectStore(self.project_path).insert_one({
            '_id': self.project_id,
            'user_id': self.user_id,
            'project_name': 'Planner-linked house',
            'plot_length': 30,
            'plot_width': 40,
            'unit': 'ft',
            'floors': 2,
            'rooms': {'Bedroom': 1},
            'room_dimensions': {'Bedroom': {'width': 12, 'depth': 10, 'height': 9}},
            'layout_data': {'Bedroom': [{'x': 60, 'y': 60}]},
        })
        self.client = app.test_client()
        self.store_patches = [
            patch('app._mongo_available', return_value=False),
            patch('app.PROJECT_STORE_PATH', self.project_path),
            patch('app.RESOURCE_STORE_PATH', self.resource_path),
        ]
        for item in self.store_patches:
            item.start()
        self.addCleanup(self.temporary_directory.cleanup)
        self.addCleanup(self._stop_patches)

    def _stop_patches(self):
        for item in reversed(self.store_patches):
            item.stop()

    def login_as(self, user_id):
        with self.client.session_transaction() as session:
            session['user_id'] = user_id
            session['user_role'] = 'user'

    def test_studio_reuses_selected_planner_dimensions_and_layout(self):
        self.login_as(self.user_id)

        response = self.client.get(f'/structural-design?project_id={self.project_id}')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Planner-linked house', response.data)
        self.assertIn(b'data-plot-length="30"', response.data)
        self.assertIn(b'"Bedroom"', response.data)
        self.assertIn(b'3D construction simulation', response.data)

    def test_structural_design_saves_per_project_and_downloads_pdf(self):
        self.login_as(self.user_id)
        payload = {
            'name': 'Foundation option A',
            'design_data': {
                'footing_type': 'isolated',
                'footing_count': 4,
                'footing_length': 5,
                'footing_width': 5,
                'footing_depth': 1.5,
                'foundation_depth': 3,
                'column_width': 1,
                'column_depth': 1,
                'footing_main_bars_x': 8,
                'concrete_grade': 'M20',
            },
            'rates': {'wastage': '5', 'excavation': ''},
        }

        invalid = self.client.post(
            f'/api/structural_designs?project_id={self.project_id}',
            json={'name': 'Bad design', 'design_data': []},
        )
        self.assertEqual(invalid.status_code, 400)

        saved = self.client.post(
            f'/api/structural_designs?project_id={self.project_id}',
            json=payload,
        )
        self.assertEqual(saved.status_code, 201)
        design_id = saved.get_json()['item']['id']
        self.assertEqual(saved.get_json()['item']['project_id'], self.project_id)

        pdf = self.client.get(f'/structural-design/drawing/{design_id}.pdf')
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf.mimetype, 'application/pdf')
        self.assertTrue(pdf.data.startswith(b'%PDF'))

        self.login_as('another-user')
        private_design = self.client.get(f'/api/structural_designs/{design_id}')
        private_pdf = self.client.get(f'/structural-design/drawing/{design_id}.pdf')
        self.assertEqual(private_design.status_code, 404)
        self.assertEqual(private_pdf.status_code, 404)

    def test_studio_requires_login_and_rejects_another_project_id(self):
        self.assertEqual(self.client.get('/structural-design').status_code, 302)

        self.login_as(self.user_id)
        response = self.client.get('/structural-design?project_id=not-owned')
        self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
