import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app
from material_estimation import (
    EstimationError,
    calculate_concrete,
    calculate_estimate,
    calculate_steel_bars,
    normalize_rate_record,
)


class ConcreteEstimationTests(unittest.TestCase):
    def test_nominal_mix_calculates_materials_and_explains_formula(self):
        estimate = calculate_concrete(1, 'M10', wastage_percent=0)

        self.assertEqual(estimate['mix_type'], 'nominal')
        self.assertEqual(estimate['cement_bags'], 5)
        self.assertAlmostEqual(estimate['sand_cft'], 16.33, places=2)
        self.assertAlmostEqual(estimate['aggregate_cft'], 32.64, places=2)
        self.assertAlmostEqual(estimate['water_litres'], 110.88, places=2)
        self.assertIn('1 m³ wet × 1.54 dry factor', estimate['formula'])

    def test_nominal_grades_use_expected_distinct_ratios(self):
        expected = {'M10': (3, 6), 'M15': (2, 4), 'M20': (1.5, 3)}
        for grade, ratios in expected.items():
            with self.subTest(grade=grade):
                result = calculate_concrete(1, grade)
                self.assertEqual((result['mix_ratio']['sand'], result['mix_ratio']['aggregate']), ratios)

    def test_custom_grade_requires_explicit_design_mix(self):
        with self.assertRaisesRegex(EstimationError, 'requires explicit design-mix'):
            calculate_concrete(1, 'M25')

        custom = calculate_concrete(1, 'M25', {'cement': 1, 'sand': 1, 'aggregate': 2})
        self.assertEqual(custom['mix_type'], 'design')

    def test_concrete_dimensions_and_wastage_roll_into_component_summary(self):
        result = calculate_estimate({
            'wastage_percent': 0,
            'components': [{
                'type': 'slab', 'quantity': 1,
                'length_m': 4, 'width_m': 5, 'thickness_m': 0.15,
                'mix_grade': 'M20',
            }],
        })

        self.assertEqual(result['components'][0]['wet_volume_m3'], 3)
        self.assertEqual(result['quantities']['cement'], 25)
        self.assertGreater(result['quantities']['aggregate'], 0)

    def test_slab_openings_are_subtracted_from_concrete_volume(self):
        result = calculate_estimate({
            'wastage_percent': 0,
            'components': [{
                'type': 'slab', 'quantity': 1,
                'length_m': 4, 'width_m': 5, 'thickness_m': 0.15,
                'openings_area_m2': 0.5, 'mix_grade': 'M20',
            }],
        })

        self.assertEqual(result['components'][0]['wet_volume_m3'], 2.925)
        self.assertEqual(result['components'][0]['dimensions']['openings_area_m2'], 0.5)

        with self.assertRaisesRegex(EstimationError, 'openings area must be less'):
            calculate_estimate({
                'components': [{
                    'type': 'slab', 'length_m': 4, 'width_m': 5,
                    'thickness_m': 0.15, 'openings_area_m2': 20,
                }],
            })

    def test_component_takeoff_covers_brickwork_plaster_flooring_and_paint(self):
        result = calculate_estimate({
            'wastage_percent': 5,
            'components': [
                {'type': 'brick_wall', 'length_m': 5, 'height_m': 3, 'thickness_m': 0.2,
                 'openings_area_m2': 2},
                {'type': 'internal_plaster', 'area_m2': 30},
                {'type': 'flooring', 'area_m2': 20},
                {'type': 'painting', 'area_m2': 30, 'coats': 2, 'coverage_m2_per_litre': 10},
            ],
        })

        self.assertGreater(result['quantities']['bricks'], 0)
        self.assertGreater(result['quantities']['plaster_cement'], 0)
        self.assertAlmostEqual(result['quantities']['tiles'], 226.04, places=1)
        self.assertAlmostEqual(result['quantities']['paint'], 6.3, places=2)


class SteelAndPricingTests(unittest.TestCase):
    def test_spacing_lap_and_hook_allowance_generate_bbs_weight(self):
        result = calculate_steel_bars([{
            'component': 'Slab main bars', 'diameter_mm': 12, 'spacing_mm': 200,
            'run_length_m': 4, 'bar_length_m': 3, 'lap_length_m': 0.5,
            'hook_bend_allowance_m': 0.4,
        }])

        self.assertEqual(result['bbs'][0]['bar_count'], 21)
        self.assertEqual(result['bbs'][0]['total_length_m'], 81.9)
        self.assertAlmostEqual(result['total_steel_kg'], 72.8, places=1)

    def test_location_falls_back_to_district_and_does_not_invent_rates(self):
        location = {'country': 'India', 'state': 'Uttarakhand', 'district': 'Dehradun', 'locality': 'Mussoorie'}
        prices = [{
            'level': 'district', 'country': 'India', 'state': 'Uttarakhand',
            'district': 'Dehradun', 'rates': {'cement_per_bag': 430}, 'source': 'Supplier quotation',
            'updated_at': '2026-01-02T00:00:00+00:00',
        }]
        result = calculate_estimate({
            'project_name': 'Test house',
            'built_up_area_sqft': 1000,
            'components': [{'type': 'slab', 'length_m': 4, 'width_m': 5,
                            'thickness_m': 0.15, 'mix_grade': 'M20'}],
        }, prices)

        self.assertEqual(result['materials']['cement']['rate'], 430)
        self.assertEqual(result['materials']['cement']['level'], 'district')
        self.assertIsNone(result['materials']['steel']['rate'])
        self.assertFalse(result['costs']['complete'])
        self.assertIn('Steel / KG', result['costs']['unpriced_items'])

    def test_manual_rate_overrides_only_the_calculation_input(self):
        result = calculate_estimate({
            'components': [{'type': 'slab', 'length_m': 2, 'width_m': 2,
                            'thickness_m': 0.1, 'mix_grade': 'M20'}],
            'manual_rates': {'cement_per_bag': 400},
        })
        self.assertEqual(result['materials']['cement']['rate'], 400)
        self.assertEqual(result['materials']['cement']['source'], 'Manual user override')

    def test_rate_record_requires_source_and_parent_location(self):
        with self.assertRaisesRegex(EstimationError, 'source is required'):
            normalize_rate_record({
                'level': 'district', 'state': 'Uttarakhand', 'district': 'Dehradun',
                'rates': {'cement_per_bag': 420},
            }, 'admin@example.com')
        with self.assertRaisesRegex(EstimationError, 'parent location'):
            normalize_rate_record({
                'level': 'locality', 'locality': 'Mussoorie', 'source': 'quote',
                'rates': {'cement_per_bag': 420},
            }, 'admin@example.com')


class EstimationRouteTests(unittest.TestCase):
    def test_cost_estimator_serves_city_lists_for_all_states_and_uts(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'city-directory-user'

        page = client.get('/cost')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Uttarakhand', page.data)
        self.assertIn(b'data-city-data-url="/static/data/india-cities.json"', page.data)

        directory_response = client.get('/static/data/india-cities.json')
        self.assertEqual(directory_response.status_code, 200)
        cities = directory_response.get_json()
        self.assertEqual(len(cities), 36)
        self.assertTrue(all(cities[state] for state in cities))
        self.assertGreaterEqual(len(cities['Uttarakhand']), 80)
        self.assertTrue({'Dehradun', 'Haldwani', 'Rudrapur', 'Pithoragarh', 'Champawat'}.issubset(cities['Uttarakhand']))

    def test_admin_rates_calculation_history_and_pdf_use_existing_resource_store(self):
        client = app.test_client()
        with tempfile.TemporaryDirectory() as directory:
            with patch('app._mongo_available', return_value=False), patch(
                'app.RESOURCE_STORE_PATH', Path(directory) / 'resources.json'
            ):
                with client.session_transaction() as session:
                    session['user_id'] = 'estimator-admin'
                    session['user_email'] = 'admin@example.com'
                    session['user_role'] = 'admin'
                admin_page = client.get('/admin/material-prices')
                self.assertEqual(admin_page.status_code, 200)

                saved_rate = client.post('/api/admin/material-prices', json={
                    'level': 'state',
                    'country': 'India',
                    'state': 'Uttarakhand',
                    'source': 'Verified supplier quotation 2026-01',
                    'rates': {'cement_per_bag': 425, 'sand_per_cft': 48},
                })
                self.assertEqual(saved_rate.status_code, 200)

                with client.session_transaction() as session:
                    session['user_id'] = 'estimator-user'
                    session['user_email'] = 'user@example.com'
                    session['user_role'] = 'user'
                calculated = client.post('/api/material-estimation/calculate', json={
                    'project_name': 'Saved test estimate',
                    'country': 'India',
                    'state': 'Uttarakhand',
                    'district': 'Dehradun',
                    'locality': 'Mussoorie',
                    'components': [{
                        'type': 'slab', 'length_m': 4, 'width_m': 5,
                        'thickness_m': 0.15, 'mix_grade': 'M20',
                    }],
                })
                self.assertEqual(calculated.status_code, 200)
                history_id = calculated.get_json()['history_id']
                self.assertEqual(calculated.get_json()['estimate']['materials']['cement']['rate'], 425)
                self.assertEqual(calculated.get_json()['estimate']['materials']['cement']['level'], 'state')
                history = client.get('/api/material-estimation/history')
                self.assertEqual(history.status_code, 200)
                self.assertEqual(len(history.get_json()['items']), 1)

                pdf = client.get(f'/material-estimation/{history_id}/report.pdf')
                self.assertEqual(pdf.status_code, 200)
                self.assertEqual(pdf.mimetype, 'application/pdf')
                self.assertTrue(pdf.data.startswith(b'%PDF'))

    def test_non_admin_cannot_open_official_price_management(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session['user_id'] = 'ordinary-user'
            session['user_email'] = 'user@example.com'
            session['user_role'] = 'user'
        response = client.get('/admin/material-prices')
        self.assertEqual(response.status_code, 302)


if __name__ == '__main__':
    unittest.main()
