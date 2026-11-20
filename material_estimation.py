"""Transparent preliminary quantity and location-aware costing calculations."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone


MIX_RATIOS = {
    'M10': {'cement': 1.0, 'sand': 3.0, 'aggregate': 6.0},
    'M15': {'cement': 1.0, 'sand': 2.0, 'aggregate': 4.0},
    'M20': {'cement': 1.0, 'sand': 1.5, 'aggregate': 3.0},
}

MATERIAL_UNITS = {
    'cement': 'bag',
    'sand': 'CFT',
    'aggregate': 'CFT',
    'steel': 'KG',
    'bricks': 'piece',
    'water': 'litre',
    'tiles': 'sq ft',
    'paint': 'litre',
    'plaster_cement': 'bag',
    'plaster_sand': 'CFT',
}

PRICE_KEYS = {
    'cement': 'cement_per_bag',
    'sand': 'sand_per_cft',
    'aggregate': 'aggregate_per_cft',
    'steel': 'steel_per_kg',
    'bricks': 'bricks_per_piece',
    'tiles': 'tiles_per_sq_ft',
    'paint': 'paint_per_litre',
}

PRICE_LABELS = {
    'cement_per_bag': 'Cement / bag',
    'sand_per_cft': 'Sand / CFT',
    'aggregate_per_cft': 'Aggregate / CFT',
    'steel_per_kg': 'Steel / KG',
    'bricks_per_piece': 'Bricks / piece',
    'tiles_per_sq_ft': 'Tiles / sq ft',
    'paint_per_litre': 'Paint / litre',
    'labour_per_sq_ft': 'Labour / sq ft',
    'labour_per_day': 'Labour / day',
    'transportation_per_km_trip': 'Transportation / km / trip',
}

UTTARAKHAND_DISTRICTS = (
    'Pauri Garhwal', 'Chamoli', 'Dehradun', 'Haridwar', 'Tehri Garhwal',
    'Rudraprayag', 'Uttarkashi', 'Almora', 'Nainital', 'Bageshwar',
    'Champawat', 'Pithoragarh',
)

DRY_VOLUME_FACTOR = 1.54
CEMENT_DENSITY_KG_M3 = 1440
KG_PER_CEMENT_BAG = 50
CFT_PER_M3 = 35.3146667215
MM_PER_M = 1000
SQFT_PER_M2 = 10.7639104167


class EstimationError(ValueError):
    pass


def _number(value, label, *, minimum=0, maximum=1_000_000_000, allow_zero=True):
    if isinstance(value, bool):
        raise EstimationError(f'{label} must be a number.')
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise EstimationError(f'{label} must be a number.')
    if not math.isfinite(result) or result > maximum or result < minimum:
        raise EstimationError(f'{label} must be between {minimum:g} and {maximum:g}.')
    if not allow_zero and result <= 0:
        raise EstimationError(f'{label} must be greater than zero.')
    return result


def _positive_component_number(component, key, label, *, optional=False, default=None):
    value = component.get(key, default)
    if value in (None, '') and optional:
        return 0.0
    return _number(value, label, minimum=0, allow_zero=optional)


def _ratio_for(component):
    grade = str(component.get('mix_grade') or 'M20').strip().upper()
    if grade in MIX_RATIOS:
        return grade, MIX_RATIOS[grade], 'nominal'
    custom = component.get('mix_ratio')
    if not isinstance(custom, dict):
        raise EstimationError(f'{grade or "Other"} requires explicit design-mix ratios.')
    ratios = {
        key: _number(custom.get(key), f'{key.title()} mix ratio', minimum=0, maximum=100, allow_zero=False)
        for key in ('cement', 'sand', 'aggregate')
    }
    return grade, ratios, 'design'


def calculate_concrete(wet_volume_m3, grade='M20', mix_ratio=None, dry_volume_factor=DRY_VOLUME_FACTOR,
                       wastage_percent=0, water_cement_ratio=0.5, configured_mix_ratios=None):
    volume = _number(wet_volume_m3, 'Wet concrete volume (m³)', allow_zero=False)
    factor = _number(dry_volume_factor, 'Dry-volume factor', minimum=1, maximum=3, allow_zero=False)
    wastage = _number(wastage_percent, 'Wastage percentage', maximum=100)
    wc_ratio = _number(water_cement_ratio, 'Water-cement ratio', maximum=2, allow_zero=False)
    grade_key = str(grade or 'M20').strip().upper()
    configured = configured_mix_ratios if isinstance(configured_mix_ratios, dict) else {}
    if grade_key in MIX_RATIOS:
        ratios = configured.get(grade_key, MIX_RATIOS[grade_key])
        if not isinstance(ratios, dict):
            raise EstimationError(f'The saved {grade_key} nominal mix ratio is invalid.')
        ratios = {
            key: _number(ratios.get(key), f'{key.title()} mix ratio', minimum=0, maximum=100, allow_zero=False)
            for key in ('cement', 'sand', 'aggregate')
        }
        mix_type = 'nominal'
    else:
        if not isinstance(mix_ratio, dict):
            raise EstimationError(f'{grade_key or "Other"} requires explicit design-mix ratios.')
        ratios = {
            key: _number(mix_ratio.get(key), f'{key.title()} mix ratio', minimum=0, maximum=100, allow_zero=False)
            for key in ('cement', 'sand', 'aggregate')
        }
        mix_type = 'design'
    dry_volume = volume * factor * (1 + wastage / 100)
    total_parts = sum(ratios.values())
    cement_volume = dry_volume * ratios['cement'] / total_parts
    sand_volume = dry_volume * ratios['sand'] / total_parts
    aggregate_volume = dry_volume * ratios['aggregate'] / total_parts
    cement_kg = cement_volume * CEMENT_DENSITY_KG_M3
    return {
        'grade': grade_key,
        'mix_type': mix_type,
        'mix_ratio': ratios,
        'wet_volume_m3': round(volume, 4),
        'dry_volume_m3': round(dry_volume, 4),
        'cement_bags': math.ceil(cement_kg / KG_PER_CEMENT_BAG),
        'cement_kg': round(cement_kg, 2),
        'sand_cft': round(sand_volume * CFT_PER_M3, 3),
        'aggregate_cft': round(aggregate_volume * CFT_PER_M3, 3),
        'water_litres': round(cement_kg * wc_ratio, 2),
        'wastage_percent': wastage,
        'dry_volume_factor': factor,
        'water_cement_ratio': wc_ratio,
        'formula': (
            f'{volume:g} m³ wet × {factor:g} dry factor × (1 + {wastage:g}% wastage) '
            f'= {dry_volume:.4f} m³ dry; ratio {ratios["cement"]:g}:'
            f'{ratios["sand"]:g}:{ratios["aggregate"]:g}. Cement volume × '
            f'{CEMENT_DENSITY_KG_M3} kg/m³ ÷ {KG_PER_CEMENT_BAG} kg/bag, '
            'rounded up to whole bags.'
        ),
    }


def _component_volume(component, component_type):
    quantity = _number(component.get('quantity', 1), f'{component_type.title()} quantity',
                       minimum=1, maximum=100_000, allow_zero=False)
    if not quantity.is_integer():
        raise EstimationError(f'{component_type.title()} quantity must be a whole number.')
    quantity = int(quantity)
    if component_type in ('foundation', 'footing'):
        length = _positive_component_number(component, 'length_m', 'Length (m)', optional=False)
        width = _positive_component_number(component, 'width_m', 'Width (m)', optional=False)
        depth = _positive_component_number(component, 'depth_m', 'Depth (m)', optional=False)
        return quantity * length * width * depth
    if component_type == 'column':
        width = _positive_component_number(component, 'width_m', 'Column width (m)', optional=False)
        depth = _positive_component_number(component, 'depth_m', 'Column depth (m)', optional=False)
        height = _positive_component_number(component, 'height_m', 'Column height (m)', optional=False)
        return quantity * width * depth * height
    if component_type == 'beam':
        length = _positive_component_number(component, 'length_m', 'Beam length (m)', optional=False)
        width = _positive_component_number(component, 'width_m', 'Beam width (m)', optional=False)
        depth = _positive_component_number(component, 'depth_m', 'Beam depth (m)', optional=False)
        return quantity * length * width * depth
    if component_type == 'slab':
        length = _positive_component_number(component, 'length_m', 'Slab length (m)', optional=False)
        width = _positive_component_number(component, 'width_m', 'Slab width (m)', optional=False)
        thickness = _positive_component_number(component, 'thickness_m', 'Slab thickness (m)', optional=False)
        gross_area = length * width
        openings = _positive_component_number(
            component, 'openings_area_m2', 'Slab openings area (m²)', optional=True
        )
        if openings >= gross_area:
            raise EstimationError('Slab openings area must be less than the gross slab area.')
        return quantity * (gross_area - openings) * thickness
    raise EstimationError(f'Unsupported concrete component: {component_type}.')


def _component_count(component, label):
    count = _number(component.get('quantity', 1), f'{label} quantity',
                    minimum=1, maximum=100_000, allow_zero=False)
    if not count.is_integer():
        raise EstimationError(f'{label} quantity must be a whole number.')
    return int(count)


def calculate_steel_bars(bar_groups):
    if not isinstance(bar_groups, list) or len(bar_groups) > 200:
        raise EstimationError('Steel bar groups must be a list of at most 200 entries.')
    bbs = []
    total_weight = 0.0
    for index, bar in enumerate(bar_groups, 1):
        if not isinstance(bar, dict):
            raise EstimationError(f'Steel bar group {index} is invalid.')
        label = str(bar.get('component') or f'Bar group {index}')[:80]
        diameter = _number(bar.get('diameter_mm'), f'{label} diameter', minimum=0, maximum=100, allow_zero=False)
        lap = _number(bar.get('lap_length_m', 0), f'{label} lap length', maximum=100)
        hook = _number(bar.get('hook_bend_allowance_m', 0), f'{label} hook/bend allowance', maximum=100)
        spacing = bar.get('spacing_mm')
        if spacing not in (None, ''):
            spacing = _number(spacing, f'{label} spacing', minimum=0, maximum=10_000, allow_zero=False)
            run_length = _number(bar.get('run_length_m'), f'{label} run length', minimum=0, allow_zero=False)
            count = math.ceil(run_length * MM_PER_M / spacing) + 1
            length = _number(bar.get('bar_length_m'), f'{label} bar length', minimum=0, allow_zero=False)
        else:
            count = _number(bar.get('number_of_bars'), f'{label} number of bars',
                            minimum=1, maximum=1_000_000, allow_zero=False)
            if not count.is_integer():
                raise EstimationError(f'{label} number of bars must be a whole number.')
            count = int(count)
            length = _number(bar.get('bar_length_m'), f'{label} bar length', minimum=0, allow_zero=False)
        total_length = count * (length + lap + hook)
        weight_per_m = diameter ** 2 / 162
        weight = total_length * weight_per_m
        total_weight += weight
        bbs.append({
            'component': label,
            'diameter_mm': diameter,
            'bar_count': count,
            'length_each_m': round(length + lap + hook, 3),
            'total_length_m': round(total_length, 3),
            'weight_kg': round(weight, 3),
            'formula': f'({diameter:g}² ÷ 162) × {total_length:.3f} m',
        })
    return {'total_steel_kg': round(total_weight, 3), 'bbs': bbs}


def calculate_components(components, global_wastage=5, dry_volume_factor=DRY_VOLUME_FACTOR,
                         water_cement_ratio=0.5, configured_mix_ratios=None):
    if not isinstance(components, list) or len(components) > 200:
        raise EstimationError('Components must be a list of at most 200 entries.')
    wastage_default = _number(global_wastage, 'Wastage percentage', maximum=100)
    totals = {
        'cement': 0.0, 'sand': 0.0, 'aggregate': 0.0, 'steel': 0.0, 'bricks': 0.0,
        'water': 0.0, 'tiles': 0.0, 'paint': 0.0, 'plaster_cement': 0.0, 'plaster_sand': 0.0,
    }
    detail_rows = []
    for index, item in enumerate(components, 1):
        if not isinstance(item, dict):
            raise EstimationError(f'Component {index} is invalid.')
        kind = str(item.get('type') or '').strip().lower()
        wastage = _number(item.get('wastage_percent', wastage_default),
                          f'{kind.title()} wastage percentage', maximum=100)
        detail = {'name': str(item.get('name') or kind.replace('_', ' ').title())[:100], 'type': kind}
        if kind in {'foundation', 'footing', 'column', 'beam', 'slab'}:
            volume = _component_volume(item, kind)
            concrete = calculate_concrete(
                volume, item.get('mix_grade', 'M20'), item.get('mix_ratio'),
                item.get('dry_volume_factor', dry_volume_factor), wastage,
                item.get('water_cement_ratio', water_cement_ratio), configured_mix_ratios,
            )
            totals['cement'] += concrete['cement_kg'] / KG_PER_CEMENT_BAG
            totals['sand'] += concrete['sand_cft']
            totals['aggregate'] += concrete['aggregate_cft']
            totals['water'] += concrete['water_litres']
            detail.update({'quantity': int(item.get('quantity', 1)), 'wet_volume_m3': round(volume, 4),
                           'concrete': concrete})
        elif kind == 'brick_wall':
            length = _positive_component_number(item, 'length_m', 'Wall length (m)', optional=False)
            height = _positive_component_number(item, 'height_m', 'Wall height (m)', optional=False)
            thickness = _positive_component_number(item, 'thickness_m', 'Wall thickness (m)', optional=False)
            quantity = _component_count(item, 'Brick wall')
            openings = _positive_component_number(item, 'openings_area_m2', 'Openings area (m²)', optional=True)
            gross_area = length * height * quantity
            if openings >= gross_area:
                raise EstimationError('Openings area must be less than gross wall area.')
            net_volume = (gross_area - openings) * thickness
            brick_length = _number(item.get('brick_length_mm', 190), 'Brick length (mm)', minimum=1, maximum=1000, allow_zero=False) / 1000
            brick_height = _number(item.get('brick_height_mm', 90), 'Brick height (mm)', minimum=1, maximum=1000, allow_zero=False) / 1000
            brick_width = _number(item.get('brick_width_mm', 90), 'Brick width (mm)', minimum=1, maximum=1000, allow_zero=False) / 1000
            joint = _number(item.get('mortar_joint_mm', 10), 'Mortar joint (mm)', minimum=0, maximum=100, allow_zero=False) / 1000
            brick_count = math.ceil(net_volume / ((brick_length + joint) * (brick_height + joint) * (brick_width + joint)))
            mortar_wet = max(0, net_volume - brick_count * brick_length * brick_height * brick_width)
            mortar_dry = mortar_wet * _number(item.get('mortar_dry_factor', 1.33), 'Mortar dry-volume factor', minimum=1, maximum=3, allow_zero=False) * (1 + wastage / 100)
            cement_ratio = _number(item.get('mortar_cement_ratio', 1), 'Mortar cement ratio', minimum=0, maximum=100, allow_zero=False)
            sand_ratio = _number(item.get('mortar_sand_ratio', 6), 'Mortar sand ratio', minimum=0, maximum=100, allow_zero=False)
            cement_volume = mortar_dry * cement_ratio / (cement_ratio + sand_ratio)
            sand_volume = mortar_dry * sand_ratio / (cement_ratio + sand_ratio)
            cement_bags = math.ceil(cement_volume * CEMENT_DENSITY_KG_M3 / KG_PER_CEMENT_BAG)
            bricks = math.ceil(brick_count * (1 + wastage / 100))
            sand_cft = sand_volume * CFT_PER_M3
            totals['bricks'] += bricks
            totals['cement'] += cement_volume * CEMENT_DENSITY_KG_M3 / KG_PER_CEMENT_BAG
            totals['sand'] += sand_cft
            detail.update({'net_wall_area_m2': round(gross_area - openings, 3),
                           'masonry_volume_m3': round(net_volume, 4), 'bricks': bricks,
                           'cement_bags': cement_bags, 'sand_cft': round(sand_cft, 3),
                           'formula': 'Net wall volume ÷ modular brick volume; remaining volume is mortar.'})
        elif kind in {'internal_plaster', 'external_plaster'}:
            quantity = _component_count(item, kind.replace('_', ' ').title())
            area = _number(item.get('area_m2'), f'{kind.title()} area (m²)', minimum=0, allow_zero=False) * quantity
            thickness = _number(item.get('thickness_mm', 12), 'Plaster thickness (mm)', minimum=1, maximum=200, allow_zero=False) / 1000
            dry = area * thickness * _number(item.get('dry_volume_factor', 1.33), 'Plaster dry-volume factor', minimum=1, maximum=3, allow_zero=False) * (1 + wastage / 100)
            cement_ratio = _number(item.get('cement_ratio', 1), 'Plaster cement ratio', minimum=0, maximum=100, allow_zero=False)
            sand_ratio = _number(item.get('sand_ratio', 4), 'Plaster sand ratio', minimum=0, maximum=100, allow_zero=False)
            cement_bags = math.ceil(dry * cement_ratio / (cement_ratio + sand_ratio) * CEMENT_DENSITY_KG_M3 / KG_PER_CEMENT_BAG)
            sand_cft = dry * sand_ratio / (cement_ratio + sand_ratio) * CFT_PER_M3
            totals['plaster_cement'] += dry * cement_ratio / (cement_ratio + sand_ratio) * CEMENT_DENSITY_KG_M3 / KG_PER_CEMENT_BAG
            totals['plaster_sand'] += sand_cft
            totals['cement'] += dry * cement_ratio / (cement_ratio + sand_ratio) * CEMENT_DENSITY_KG_M3 / KG_PER_CEMENT_BAG
            totals['sand'] += sand_cft
            detail.update({'area_m2': round(area, 3), 'cement_bags': cement_bags,
                           'sand_cft': round(sand_cft, 3),
                           'formula': f'{area:g} m² × {thickness:g} m × dry factor × mix ratio.'})
        elif kind == 'flooring':
            quantity = _component_count(item, 'Flooring')
            area = _number(item.get('area_m2'), 'Flooring area (m²)', minimum=0, allow_zero=False) * quantity
            tiles = area * SQFT_PER_M2 * (1 + wastage / 100)
            totals['tiles'] += tiles
            detail.update({'area_m2': round(area, 3), 'tiles_sq_ft': round(tiles, 2),
                           'formula': f'{area:g} m² × {SQFT_PER_M2:.4f} sq ft/m² × (1 + {wastage:g}% wastage).'})
        elif kind == 'painting':
            quantity = _component_count(item, 'Painting')
            area = _number(item.get('area_m2'), 'Paint area (m²)', minimum=0, allow_zero=False) * quantity
            coats = _number(item.get('coats', 2), 'Paint coats', minimum=1, maximum=20, allow_zero=False)
            if not coats.is_integer():
                raise EstimationError('Paint coats must be a whole number.')
            coverage = _number(item.get('coverage_m2_per_litre', 10), 'Paint coverage (m²/litre)', minimum=0, allow_zero=False)
            litres = area * int(coats) / coverage * (1 + wastage / 100)
            totals['paint'] += litres
            detail.update({'area_m2': round(area, 3), 'coats': int(coats), 'paint_litres': round(litres, 3),
                           'formula': f'{area:g} m² × {int(coats)} coats ÷ {coverage:g} m²/litre × wastage.'})
        else:
            raise EstimationError(f'Unsupported component type: {kind or "(missing)"}.')
        dimension_fields = {
            'foundation': ('length_m', 'width_m', 'depth_m'),
            'footing': ('length_m', 'width_m', 'depth_m'),
            'column': ('width_m', 'depth_m', 'height_m'),
            'beam': ('length_m', 'width_m', 'depth_m'),
            'slab': ('length_m', 'width_m', 'thickness_m', 'openings_area_m2'),
            'brick_wall': (
                'length_m', 'height_m', 'thickness_m', 'openings_area_m2',
                'brick_length_mm', 'brick_height_mm', 'brick_width_mm', 'mortar_joint_mm',
            ),
            'internal_plaster': ('area_m2', 'thickness_mm'),
            'external_plaster': ('area_m2', 'thickness_mm'),
            'flooring': ('area_m2',),
            'painting': ('area_m2', 'coats', 'coverage_m2_per_litre'),
        }
        detail['dimensions'] = {
            key: round(float(item[key]), 3)
            for key in dimension_fields[kind]
            if item.get(key) not in (None, '')
        }
        detail['quantity'] = _component_count(item, detail['name']) if item.get('quantity') is not None else 1
        detail_rows.append(detail)

    steel = calculate_steel_bars([])
    return {
        'components': detail_rows,
        'quantities': {
            'cement': math.ceil(totals['cement']),
            'sand': round(totals['sand'], 3),
            'aggregate': round(totals['aggregate'], 3),
            'steel': steel['total_steel_kg'],
            'bricks': math.ceil(totals['bricks']),
            'water': round(totals['water'], 2),
            'tiles': round(totals['tiles'], 2),
            'paint': round(totals['paint'], 3),
            'plaster_cement': math.ceil(totals['plaster_cement']),
            'plaster_sand': round(totals['plaster_sand'], 3),
        },
        'steel_bbs': steel['bbs'],
        'assumptions': [
            'Nominal M10/M15/M20 proportions are estimation ratios, not structural design-mix specifications.',
            'Other concrete grades require user-supplied design-mix proportions; no design mix is inferred.',
            'Concrete quantity is derived from the entered geometry. Do not enter overlapping component volumes twice.',
            'Cement is combined by mass before whole-bag rounding; component subtotals can differ from the combined total due to rounding.',
            'Steel is a preliminary quantity estimate and must be checked against structural drawings and engineer-approved BBS.',
            'Coverage, wastage, mortar ratios and dry-volume factors are editable assumptions, not guaranteed site yields.',
        ],
    }


def calculate_estimate(payload, price_records=()):
    if not isinstance(payload, dict):
        raise EstimationError('Estimation data must be an object.')
    components = payload.get('components', [])
    steel_bars = payload.get('steel_bars', [])
    if not components and not steel_bars:
        raise EstimationError('Enter at least one component or steel bar group.')
    global_wastage = _number(payload.get('wastage_percent', 5), 'Wastage percentage', maximum=100)
    dry_factor = _number(payload.get('dry_volume_factor', DRY_VOLUME_FACTOR), 'Dry-volume factor', minimum=1, maximum=3, allow_zero=False)
    water_cement_ratio = _number(payload.get('water_cement_ratio', 0.5), 'Water-cement ratio', maximum=2, allow_zero=False)
    configured_ratios = payload.get('configured_mix_ratios')
    result = calculate_components(
        components, global_wastage, dry_factor, water_cement_ratio,
        configured_ratios,
    )
    steel = calculate_steel_bars(steel_bars)
    result['quantities']['steel'] = steel['total_steel_kg']
    result['steel_bbs'] = steel['bbs']
    result['project'] = {
        'name': str(payload.get('project_name') or 'Untitled project').strip()[:120],
        'country': str(payload.get('country') or 'India').strip()[:80],
        'state': str(payload.get('state') or 'Uttarakhand').strip()[:80],
        'district': str(payload.get('district') or '').strip()[:100],
        'locality': str(payload.get('locality') or '').strip()[:100],
    }
    area = _number(payload.get('built_up_area_sqft', 0), 'Built-up area (sq ft)', maximum=100_000_000)
    if area == 0:
        for component in components:
            if not isinstance(component, dict):
                continue
            kind = component.get('type')
            count = _component_count(component, str(kind or 'Component')) if component.get('quantity') is not None else 1
            if kind == 'flooring' and component.get('area_m2') not in (None, ''):
                area += _number(component['area_m2'], 'Component area (m²)', maximum=100_000_000) * count * SQFT_PER_M2
            elif kind == 'slab':
                area += (
                    _number(component.get('length_m'), 'Slab length (m)', allow_zero=False)
                    * _number(component.get('width_m'), 'Slab width (m)', allow_zero=False)
                    * count * SQFT_PER_M2
                )
    result['project']['built_up_area_sqft'] = round(area, 2)
    location = result['project']
    rates, price_sources = resolve_prices(location, price_records, payload.get('manual_rates', {}))
    materials = {}
    material_total = 0.0
    priced_count = 0
    unpriced = []
    for material, price_key in PRICE_KEYS.items():
        quantity = result['quantities'][material]
        price = rates.get(price_key)
        amount = round(quantity * price['rate'], 2) if price and price.get('rate') is not None else None
        if amount is not None:
            material_total += amount
            priced_count += 1
        elif quantity:
            unpriced.append(PRICE_LABELS[price_key])
        materials[material] = {
            'quantity': quantity, 'unit': MATERIAL_UNITS[material],
            'rate': price.get('rate') if price else None, 'amount': amount,
            'source': price.get('source') if price else None,
            'updated_at': price.get('updated_at') if price else None,
            'level': price.get('level') if price else None,
        }
    catalog = {
        str(item.get('id') or item.get('_id')): item
        for item in payload.get('custom_material_catalog', [])
        if isinstance(item, dict) and (item.get('id') or item.get('_id'))
    }
    custom_materials = payload.get('custom_materials', [])
    if not isinstance(custom_materials, list) or len(custom_materials) > 100:
        raise EstimationError('Custom material entries must be a list of at most 100 items.')
    custom_material_rows = []
    custom_material_total = 0.0
    for index, entry in enumerate(custom_materials, 1):
        if not isinstance(entry, dict):
            raise EstimationError(f'Custom material entry {index} is invalid.')
        catalog_id = str(entry.get('catalog_id') or '')
        material = catalog.get(catalog_id)
        if not material:
            raise EstimationError(f'Custom material entry {index} is not in the authorized material catalogue.')
        quantity = _number(entry.get('quantity'), f"{material.get('name', 'Material')} quantity",
                           minimum=0, maximum=1_000_000_000, allow_zero=False)
        price_key = f'custom_{catalog_id}'
        if entry.get('unit_price') not in (None, ''):
            price = {
                'rate': _number(entry['unit_price'], f"{material.get('name', 'Material')} unit price",
                                maximum=1_000_000_000),
                'source': 'Manual user override', 'updated_at': None, 'level': 'manual',
            }
        else:
            price = _lookup_service_price(price_key, location, price_records, {})
        amount = round(quantity * price['rate'], 2) if price else None
        if amount is not None:
            custom_material_total += amount
        elif quantity:
            unpriced.append(f"{material.get('name', 'Material')} ({material.get('unit', 'unit')})")
        custom_material_rows.append({
            'catalog_id': catalog_id,
            'name': str(material.get('name') or '')[:100],
            'unit': str(material.get('unit') or 'unit')[:40],
            'quantity': quantity,
            'rate': price.get('rate') if price else None,
            'amount': amount,
            'source': price.get('source') if price else None,
            'updated_at': price.get('updated_at') if price else None,
            'level': price.get('level') if price else None,
        })
    labour_area = _number(payload.get('labour_area_sqft', area), 'Labour area (sq ft)', maximum=100_000_000)
    labour_days = _number(payload.get('labour_days', 0), 'Labour days', maximum=1_000_000)
    labour_price = _lookup_service_price('labour_per_sq_ft', location, price_records, payload.get('manual_rates', {}))
    labour_cost = (
        round(labour_area * labour_price['rate'], 2)
        if labour_area and labour_price and labour_price.get('rate') is not None else None
    )
    if labour_cost is None and labour_days:
        daily_rate = _lookup_service_price('labour_per_day', location, price_records, payload.get('manual_rates', {}))
        if daily_rate and daily_rate.get('rate') is not None:
            labour_cost = round(labour_days * daily_rate['rate'], 2)
            labour_price = daily_rate
    distance = _number(payload.get('transport_distance_km', 0), 'Transportation distance (km)', maximum=1_000_000)
    trips = _number(payload.get('transport_trips', 0), 'Transportation trips', maximum=1_000_000)
    if bool(distance) != bool(trips):
        raise EstimationError('Enter both transportation distance and trip count, or leave both at zero.')
    transport_price = _lookup_service_price('transportation_per_km_trip', location, price_records, payload.get('manual_rates', {}))
    transport_cost = round(distance * trips * transport_price['rate'], 2) if transport_price and transport_price.get('rate') is not None else None
    equipment = _number(payload.get('equipment_cost', 0), 'Equipment cost', maximum=1_000_000_000_000)
    other_materials = _number(payload.get('other_material_cost', 0), 'Other material cost', maximum=1_000_000_000_000)
    other = _number(payload.get('other_expenses', 0), 'Other expenses', maximum=1_000_000_000_000)
    priced_costs = [material_total, custom_material_total, other_materials, equipment, other]
    if labour_cost is not None:
        priced_costs.append(labour_cost)
    if transport_cost is not None:
        priced_costs.append(transport_cost)
    known_total = round(sum(priced_costs), 2)
    missing_costs = list(unpriced)
    if labour_cost is None and (labour_area or labour_days):
        missing_costs.append('Labour')
    if distance and trips and transport_cost is None:
        missing_costs.append('Transportation')
    result.update({
        'materials': materials,
        'custom_materials': custom_material_rows,
        'price_sources': price_sources,
        'service_prices': {
            'labour': labour_price,
            'transportation': transport_price,
        },
        'costs': {
            'material_cost': round(material_total, 2),
            'custom_material_cost': round(custom_material_total, 2),
            'other_material_cost': other_materials,
            'labour_cost': labour_cost,
            'transportation_cost': transport_cost,
            'equipment_cost': equipment,
            'other_expenses': other,
            'known_total': known_total,
            'complete': not missing_costs,
            'unpriced_items': missing_costs,
            'cost_per_sq_ft': round(known_total / area, 2) if area else None,
            'cost_per_sq_m': round(known_total / (area / SQFT_PER_M2), 2) if area else None,
        },
        'pricing_location': location,
        'price_updated_at': max(
            (
                item.get('updated_at')
                for item in [*rates.values(), labour_price, transport_price]
                if item and item.get('updated_at')
            ),
            default=None,
        ),
    })
    return result


def resolve_prices(location, price_records, manual_rates=None):
    keys = ('country', 'state', 'district', 'locality')
    target = {key: str(location.get(key) or '').strip().casefold() for key in keys}
    manual = _normalize_manual_rates(manual_rates)
    rates = {}
    sources = {}
    records = [record for record in price_records if isinstance(record, dict)]
    for price_key in tuple(PRICE_LABELS):
        if manual.get(price_key) is not None:
            rates[price_key] = {'rate': manual[price_key], 'source': 'Manual user override',
                                'updated_at': None, 'level': 'manual'}
            sources[price_key] = rates[price_key]
            continue
        matches = []
        for record in records:
            level = str(record.get('level') or '').strip().lower()
            match_keys = keys[:{'country': 1, 'state': 2, 'district': 3, 'locality': 4}.get(level, 0)]
            record_location = {key: str(record.get(key) or '').strip().casefold() for key in keys}
            if not match_keys or any(not target[key] or target[key] != record_location[key] for key in match_keys):
                continue
            rate = (record.get('rates') or {}).get(price_key)
            if rate is None:
                continue
            matches.append((len(match_keys), record, rate))
        if matches:
            _, record, rate = max(matches, key=lambda match: match[0])
            rate_value = _number(rate, PRICE_LABELS[price_key], maximum=1_000_000_000)
            resolved = {
                'rate': rate_value,
                'source': str(record.get('source') or 'Admin-entered quote'),
                'updated_at': record.get('updated_at'),
                'level': record.get('level'),
            }
            rates[price_key] = resolved
            sources[price_key] = resolved
    return rates, sources


def _normalize_manual_rates(manual_rates):
    if not isinstance(manual_rates, dict):
        return {}
    output = {}
    for key in PRICE_LABELS:
        value = manual_rates.get(key)
        if value in (None, ''):
            continue
        output[key] = _number(value, f'Manual {PRICE_LABELS[key]}', maximum=1_000_000_000)
    return output


def _lookup_service_price(key, location, price_records, manual_rates):
    manual = _normalize_manual_rates(manual_rates)
    if manual.get(key) is not None:
        return {'rate': manual[key], 'source': 'Manual user override', 'updated_at': None, 'level': 'manual'}
    records = [record for record in price_records if isinstance(record, dict)]
    keys = ('country', 'state', 'district', 'locality')
    target = {part: str(location.get(part) or '').strip().casefold() for part in keys}
    matches = []
    for record in records:
        level = str(record.get('level') or '').strip().lower()
        match_keys = keys[:{'country': 1, 'state': 2, 'district': 3, 'locality': 4}.get(level, 0)]
        record_location = {part: str(record.get(part) or '').strip().casefold() for part in keys}
        if not match_keys or any(not target[part] or target[part] != record_location[part] for part in match_keys):
            continue
        rate = (record.get('rates') or {}).get(key)
        if rate is not None:
            matches.append((len(match_keys), record, rate))
    if not matches:
        return None
    _, record, rate = max(matches, key=lambda match: match[0])
    return {'rate': _number(rate, PRICE_LABELS.get(key, key), maximum=1_000_000_000),
            'source': str(record.get('source') or 'Admin-entered quote'),
            'updated_at': record.get('updated_at'), 'level': record.get('level')}


def normalize_rate_record(payload, actor):
    if not isinstance(payload, dict):
        raise EstimationError('Price record must be an object.')
    level = str(payload.get('level') or '').strip().lower()
    if level not in {'country', 'state', 'district', 'locality'}:
        raise EstimationError('Choose a valid price location level.')
    country = str(payload.get('country') or 'India').strip()[:80]
    state = str(payload.get('state') or '').strip()[:80]
    district = str(payload.get('district') or '').strip()[:100]
    locality = str(payload.get('locality') or '').strip()[:100]
    required = {'state': state, 'district': district, 'locality': locality}
    hierarchy = {'country': 0, 'state': 1, 'district': 2, 'locality': 3}
    if any(not required[key] for key in ('state', 'district', 'locality')[:hierarchy[level]]):
        raise EstimationError('Fill each parent location before adding a more specific rate.')
    rates = payload.get('rates') or {}
    if not isinstance(rates, dict):
        raise EstimationError('Rates must be an object.')
    clean_rates = {}
    allowed = tuple(PRICE_LABELS)
    for key in allowed:
        value = rates.get(key)
        if value in (None, ''):
            continue
        clean_rates[key] = _number(value, PRICE_LABELS[key], maximum=1_000_000_000)
    for key, value in rates.items():
        if not isinstance(key, str) or not re.fullmatch(r'custom_[A-Za-z0-9_-]{1,80}', key):
            continue
        if value not in (None, ''):
            clean_rates[key] = _number(value, f'Custom material rate {key[7:]}', maximum=1_000_000_000)
    if not clean_rates:
        raise EstimationError('Enter at least one sourced material, labour, or transportation rate.')
    source = str(payload.get('source') or '').strip()[:200]
    if not source:
        raise EstimationError('Rate source is required; do not save an unsourced price as an official rate.')
    stamp = datetime.now(timezone.utc).isoformat()
    return {
        'record_type': 'material_price',
        'level': level,
        'country': country,
        'state': state if hierarchy[level] >= 1 else '',
        'district': district if hierarchy[level] >= 2 else '',
        'locality': locality if hierarchy[level] >= 3 else '',
        'rates': clean_rates,
        'source': source,
        'updated_at': stamp,
        'updated_by': str(actor),
        'history': [{
            'rates': clean_rates, 'source': source, 'updated_at': stamp, 'updated_by': str(actor),
        }],
    }
