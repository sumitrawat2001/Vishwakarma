import math


DIRECTIONS = ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')
DIRECTION_LABELS = {
    'N': 'North',
    'NE': 'Northeast',
    'E': 'East',
    'SE': 'Southeast',
    'S': 'South',
    'SW': 'Southwest',
    'W': 'West',
    'NW': 'Northwest',
}

VASTU_RULES = {
    'main_entrance': {
        'label': 'Main entrance',
        'preferred': 'N',
        'alternatives': ['NE', 'E'],
        'weight': 1.5,
        'description': 'Traditional preference for the placement of the main entrance.',
        'source': 'Unverified traditional preference; no named source has been independently verified.',
        'category': 'Entrance placement',
        'applicable_conditions': 'General residential reference only; confirm orientation and site context.',
        'recommendation': 'Consider this placement only if it suits the plan and the tradition you follow.',
    },
    'kitchen': {
        'label': 'Kitchen',
        'preferred': 'SE',
        'alternatives': ['NW'],
        'weight': 1.0,
        'description': 'Traditional preference for kitchen placement.',
        'source': 'Unverified traditional preference; no named source has been independently verified.',
        'category': 'Room placement',
        'applicable_conditions': 'General residential reference only; confirm ventilation, services, and site context.',
        'recommendation': 'Consider this placement only if it suits the plan and the tradition you follow.',
    },
    'master_bedroom': {
        'label': 'Master bedroom',
        'preferred': 'SW',
        'alternatives': ['S', 'W'],
        'weight': 1.0,
        'description': 'Traditional preference for master bedroom placement.',
        'source': 'Unverified traditional preference; no named source has been independently verified.',
        'category': 'Room placement',
        'applicable_conditions': 'General residential reference only; confirm the actual plan and site context.',
        'recommendation': 'Consider this placement only if it suits the plan and the tradition you follow.',
    },
    'living_room': {
        'label': 'Living room',
        'preferred': 'NE',
        'alternatives': ['N', 'E', 'NW'],
        'weight': 1.0,
        'description': 'Traditional preference for living room placement.',
        'source': 'Unverified traditional preference; no named source has been independently verified.',
        'category': 'Room placement',
        'applicable_conditions': 'General residential reference only; confirm the actual plan and site context.',
        'recommendation': 'Consider this placement only if it suits the plan and the tradition you follow.',
    },
    'pooja_room': {
        'label': 'Pooja room',
        'preferred': 'NE',
        'alternatives': ['N', 'E'],
        'weight': 1.0,
        'description': 'Traditional preference for pooja room placement.',
        'source': 'Unverified traditional preference; no named source has been independently verified.',
        'category': 'Room placement',
        'applicable_conditions': 'General residential reference only; confirm the actual plan and site context.',
        'recommendation': 'Consider this placement only if it suits the plan and the tradition you follow.',
    },
    'bathroom_toilet': {
        'label': 'Bathroom / toilet',
        'preferred': 'NW',
        'alternatives': ['W', 'S'],
        'weight': 1.0,
        'description': 'Traditional preference for bathroom or toilet placement.',
        'source': 'Unverified traditional preference; no named source has been independently verified.',
        'category': 'Room placement',
        'applicable_conditions': 'General residential reference only; sanitation, plumbing, and building codes take priority.',
        'recommendation': 'Do not compromise sanitation, plumbing, accessibility, or applicable building requirements.',
    },
    'staircase': {
        'label': 'Staircase',
        'preferred': 'S',
        'alternatives': ['W', 'SW'],
        'weight': 1.0,
        'description': 'Traditional preference for staircase placement.',
        'source': 'Unverified traditional preference; no named source has been independently verified.',
        'category': 'Room placement',
        'applicable_conditions': 'General residential reference only; structural design and safe egress take priority.',
        'recommendation': 'Do not compromise structural design, safe egress, or applicable building requirements.',
    },
    'overhead_water_tank': {
        'label': 'Overhead water tank',
        'preferred': 'SW',
        'alternatives': ['W'],
        'weight': 1.0,
        'description': 'Traditional preference for overhead water tank placement.',
        'source': 'Unverified traditional preference; no named source has been independently verified.',
        'category': 'Water placement',
        'applicable_conditions': 'General residential reference only; confirm structural loading and waterproofing professionally.',
        'recommendation': 'Have structural loading and waterproofing checked by a qualified professional.',
    },
    'underground_water_source': {
        'label': 'Underground water source',
        'preferred': 'NE',
        'alternatives': ['N', 'E'],
        'weight': 1.0,
        'description': 'Traditional preference for underground water source placement.',
        'source': 'Unverified traditional preference; no named source has been independently verified.',
        'category': 'Water placement',
        'applicable_conditions': 'General residential reference only; confirm groundwater, sanitation setbacks, and local rules.',
        'recommendation': 'Check water quality, groundwater conditions, sanitation setbacks, and local rules.',
    },
}

for _rule in VASTU_RULES.values():
    _rule['preferred_labels'] = [DIRECTION_LABELS[_rule['preferred']]]
    _rule['alternative_labels'] = [DIRECTION_LABELS[item] for item in _rule['alternatives']]

STANDARD_RULE_LIBRARY = {
    key: {
        **rule,
        'component': key,
        'preferred_directions': [rule['preferred']],
        'preferred_labels': [DIRECTION_LABELS[rule['preferred']]],
        'alternative_labels': [DIRECTION_LABELS[item] for item in rule['alternatives']],
        'priority': 'high' if key == 'main_entrance' else 'medium',
        'enabled': True,
        'rule_name': rule['label'],
    }
    for key, rule in VASTU_RULES.items()
}

VASTU_COMPONENTS = {
    key: rule['label'] for key, rule in VASTU_RULES.items()
}

PRIORITY_WEIGHTS = {'low': 1.0, 'medium': 2.0, 'high': 3.0}

ROOM_RULES = {
    'Kitchen': 'kitchen',
    'Master Bedroom': 'master_bedroom',
    'Living Room': 'living_room',
    'Pooja Room': 'pooja_room',
    'Bathroom': 'bathroom_toilet',
    'Toilet': 'bathroom_toilet',
    'Bathroom / Toilet': 'bathroom_toilet',
    'Staircase': 'staircase',
    'Water Tank': 'overhead_water_tank',
    'Overhead Water Tank': 'overhead_water_tank',
    'Underground Water Source': 'underground_water_source',
    'Borewell': 'underground_water_source',
}


def analyze_rule_sets(room_directions, custom_rules=None, mode='standard', standard_rules=None):
    """Compare known room directions against the selected traditional rule sets."""
    if mode not in {'standard', 'custom', 'combined'}:
        raise ValueError('Choose Standard, Custom, or Combined Vastu mode.')

    directions = room_directions if isinstance(room_directions, dict) else {}
    configured_standard_rules = STANDARD_RULE_LIBRARY.values() if standard_rules is None else standard_rules
    active_standard_rules = [
        rule for rule in configured_standard_rules
        if isinstance(rule, dict) and rule.get('enabled', True)
    ]
    active_custom_rules = [
        rule for rule in (custom_rules or [])
        if isinstance(rule, dict) and rule.get('enabled', True)
    ]
    rules = []
    if mode in {'standard', 'combined'}:
        rules.extend(
            {
                **rule,
                'rule_id': str(rule.get('id') or rule.get('rule_id') or f"standard:{rule.get('component', 'unknown')}"),
                'rule_type': 'standard',
            }
            for rule in active_standard_rules
        )
    if mode in {'custom', 'combined'}:
        rules.extend(
            {**rule, 'rule_id': str(rule.get('id') or rule.get('_id') or ''), 'rule_type': 'custom'}
            for rule in active_custom_rules
        )

    by_component = {}
    for rule in rules:
        by_component.setdefault(rule.get('component'), []).append(rule)
    conflicts = []
    conflicting_ids = set()
    for component, component_rules in by_component.items():
        preference_sets = [
            set(rule.get('preferred_directions') or ([rule['preferred']] if rule.get('preferred') else []))
            for rule in component_rules
        ]
        if len(preference_sets) > 1 and not set.intersection(*preference_sets):
            conflict = {
                'component': component,
                'label': VASTU_COMPONENTS.get(component, str(component or 'Unknown component')),
                'rule_names': [rule.get('rule_name') or rule.get('label') or 'Unnamed rule' for rule in component_rules],
                'preferred_directions': [sorted(preferences) for preferences in preference_sets],
            }
            conflicts.append(conflict)
            conflicting_ids.update(rule['rule_id'] for rule in component_rules)

    results = []
    assessed_weight = 0.0
    earned_weight = 0.0
    counts = {
        'matches': 0,
        'partial_matches': 0,
        'differs': 0,
        'insufficient': 0,
    }
    for rule in rules:
        component = rule.get('component')
        selected = directions.get(component)
        if selected not in DIRECTIONS:
            category = 'insufficient'
            explanation = 'Room direction is not available; this rule is excluded from the score.'
            counts['insufficient'] += 1
        else:
            preferred = rule.get('preferred_directions') or ([rule.get('preferred')] if rule.get('preferred') else [])
            alternatives = rule.get('alternative_directions') or rule.get('alternatives') or []
            weight = float(rule.get('weight') or PRIORITY_WEIGHTS.get(rule.get('priority'), 2.0))
            assessed_weight += weight
            if selected in preferred:
                category = 'matches'
                earned_weight += weight
                explanation = f"Actual direction {DIRECTION_LABELS[selected]} matches the selected preferred direction."
                counts['matches'] += 1
            elif selected in alternatives:
                category = 'partial'
                earned_weight += weight * 0.5
                explanation = f"Actual direction {DIRECTION_LABELS[selected]} is listed as an acceptable alternative."
                counts['partial_matches'] += 1
            else:
                category = 'differs'
                preferred_labels = ', '.join(DIRECTION_LABELS[item] for item in preferred if item in DIRECTION_LABELS) or 'not set'
                explanation = f"Actual direction {DIRECTION_LABELS[selected]} differs from the preferred direction ({preferred_labels})."
                counts['differs'] += 1

        preferred_directions = rule.get('preferred_directions') or ([rule.get('preferred')] if rule.get('preferred') else [])
        alternative_directions = rule.get('alternative_directions') or rule.get('alternatives') or []
        results.append({
            'rule_id': rule['rule_id'],
            'rule_type': rule['rule_type'],
            'rule_name': rule.get('rule_name') or rule.get('label') or 'Unnamed rule',
            'component': component,
            'component_label': VASTU_COMPONENTS.get(component, str(component or 'Unknown component')),
            'actual_direction': selected,
            'actual_direction_label': DIRECTION_LABELS.get(selected, 'Insufficient data'),
            'preferred_directions': preferred_directions,
            'preferred_labels': [DIRECTION_LABELS[item] for item in preferred_directions if item in DIRECTION_LABELS],
            'alternative_directions': alternative_directions,
            'alternative_labels': [DIRECTION_LABELS[item] for item in alternative_directions if item in DIRECTION_LABELS],
            'status': category,
            'status_label': {
                'matches': 'Matches Selected Rule',
                'partial': 'Partially Matches',
                'differs': 'Differs from Selected Rule',
                'insufficient': 'Insufficient Data',
            }[category],
            'explanation': explanation,
            'recommendation': rule.get('recommendation') or '',
            'traditional_recommendation': (
                f"Configured traditional preference: "
                f"{', '.join(DIRECTION_LABELS[item] for item in preferred_directions if item in DIRECTION_LABELS) or 'not set'}."
            ),
            'suggested_improvement': rule.get('recommendation') or (
                f"If practical, review the placement against the preferred direction "
                f"({', '.join(DIRECTION_LABELS[item] for item in preferred_directions if item in DIRECTION_LABELS) or 'not set'})."
                if category != 'matches'
                else 'No change is suggested by this selected rule.'
            ),
            'alternative_if_relocation_not_possible': rule.get('alternative_if_relocation_not_possible') or (
                'If moving the room is not practical, keep the current layout and prioritize ventilation, '
                'sanitation, privacy, accessibility, structure, and local building requirements. No remedy is guaranteed.'
            ),
            'description': rule.get('description') or '',
            'source': rule.get('source') or 'User-defined rule',
            'source_status': rule.get('source_status') or ('unverified' if rule['rule_type'] == 'standard' else 'user_defined'),
            'category': rule.get('category') or 'User-defined',
            'applicable_conditions': rule.get('applicable_conditions') or '',
            'priority': rule.get('priority') or 'medium',
            'conflict': rule['rule_id'] in conflicting_ids,
        })

    score = round(earned_weight / assessed_weight * 100) if assessed_weight else None
    return {
        'mode': mode,
        'rules': results,
        'conflicts': conflicts,
        **counts,
        'assessed_count': sum(counts[key] for key in ('matches', 'partial_matches', 'differs')),
        'total_rules': len(rules),
        'score': score,
        'earned_weight': round(earned_weight, 2),
        'assessed_weight': round(assessed_weight, 2),
        'calculation_method': (
            'Application-defined rule-match score: matched rules receive their full priority weight, '
            'partial matches receive half weight, differing rules receive zero, and insufficient-data '
            'rules are excluded. Earned weight is divided by assessed weight and multiplied by 100.'
        ),
    }


def _valid_coordinate(value):
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def directions_from_layout(layout_data, north_direction='N'):
    """Convert saved SVG canvas positions to compass sectors."""
    if not isinstance(layout_data, dict) or north_direction not in DIRECTIONS:
        return {}

    north_offset = DIRECTIONS.index(north_direction)
    derived = {}
    for room_name, positions in layout_data.items():
        rule_key = ROOM_RULES.get(str(room_name).strip())
        if not rule_key or not isinstance(positions, list):
            continue

        valid_positions = [
            position for position in positions
            if isinstance(position, dict)
            and _valid_coordinate(position.get('x'))
            and _valid_coordinate(position.get('y'))
        ]
        if not valid_positions:
            continue

        room_directions = []
        for position in valid_positions:
            dx = float(position['x']) - 360
            dy = 250 - float(position['y'])
            if dx == 0 and dy == 0:
                continue
            angle = math.degrees(math.atan2(dx, dy)) % 360
            canvas_sector = int((angle + 22.5) // 45) % len(DIRECTIONS)
            room_directions.append(DIRECTIONS[(canvas_sector + north_offset) % len(DIRECTIONS)])

        if room_directions:
            derived[rule_key] = room_directions[0] if len(set(room_directions)) == 1 else 'Mixed'
    return derived


def analyze_vastu(
    plot_length,
    plot_width,
    plot_shape,
    north_direction,
    room_directions,
    guideline_preferences=None,
    guideline_weights=None,
    layout_data=None,
):
    """Return a deterministic, weighted comparison against configurable guidelines."""
    try:
        length = float(plot_length)
        width = float(plot_width)
    except (TypeError, ValueError):
        raise ValueError('Enter valid plot dimensions.')
    if not math.isfinite(length) or not math.isfinite(width) or not (0 < length <= 10000 and 0 < width <= 10000):
        raise ValueError('Plot dimensions must be greater than zero and no more than 10,000.')
    if plot_shape not in {'rectangular', 'square'}:
        raise ValueError('Choose rectangular or square plot shape.')
    if plot_shape == 'square' and not math.isclose(length, width, rel_tol=0.0, abs_tol=0.01):
        raise ValueError('For a square plot, length and width must be equal.')
    if north_direction not in DIRECTIONS:
        raise ValueError('Choose a valid north direction.')

    manual_directions = room_directions if isinstance(room_directions, dict) else {}
    preferences = guideline_preferences if isinstance(guideline_preferences, dict) else {}
    configured_weights = guideline_weights if isinstance(guideline_weights, dict) else {}
    layout_directions = directions_from_layout(layout_data, north_direction)

    results = []
    assessed_weight = 0.0
    matched_weight = 0.0
    matched = 0
    needs_review = 0
    missing = 0

    for key, rule in VASTU_RULES.items():
        preferred = preferences.get(key, rule['preferred'])
        if preferred not in DIRECTIONS:
            preferred = rule['preferred']
        try:
            weight = float(configured_weights.get(key, rule['weight']))
        except (TypeError, ValueError):
            raise ValueError(f"Enter a valid weight for {rule['label']}.")
        if not math.isfinite(weight) or not 0.1 <= weight <= 5:
            raise ValueError(f"Weight for {rule['label']} must be between 0.1 and 5.")

        planner_direction = layout_directions.get(key)
        selected = planner_direction
        source = 'planner layout' if planner_direction else 'manual selection'
        if selected is None or selected == 'Mixed':
            manual_direction = manual_directions.get(key)
            if manual_direction in DIRECTIONS:
                selected = manual_direction
                source = 'manual selection'
        if selected not in DIRECTIONS:
            invalid = selected not in (None, '', 'Mixed')
            message = (
                'The saved planner position spans multiple direction sectors; choose a manual direction to review it.'
                if selected == 'Mixed'
                else 'Direction not provided; select a direction to include this guideline in the score.'
            )
            if invalid:
                message = 'Invalid direction; choose one of the listed compass directions.'
            status = 'needs_review'
            missing += 1
            selected_label = 'Invalid' if invalid else 'Not provided'
            recommendation = message
        else:
            assessed_weight += weight
            if selected == preferred:
                status = 'matched'
                matched += 1
                matched_weight += weight
                recommendation = f"Matches the configured preferred direction ({DIRECTION_LABELS[preferred]})."
            else:
                status = 'needs_review'
                needs_review += 1
                alternatives = ', '.join(DIRECTION_LABELS[item] for item in rule['alternatives'])
                recommendation = (
                    f"Configured preferred direction is {DIRECTION_LABELS[preferred]}. "
                    f"Suggested traditional alternatives to consider: {alternatives}."
                )
            selected_label = DIRECTION_LABELS[selected]

        results.append({
            'key': key,
            'label': rule['label'],
            'selected_direction': selected,
            'selected_label': selected_label,
            'preferred_direction': preferred,
            'preferred_label': DIRECTION_LABELS[preferred],
            'alternatives': rule['alternatives'],
            'alternative_labels': [DIRECTION_LABELS[item] for item in rule['alternatives']],
            'weight': weight,
            'status': status,
            'source': source if selected in DIRECTIONS else 'manual selection',
            'recommendation': recommendation,
        })

    total_weight = sum(
        float(configured_weights.get(key, rule['weight']))
        for key, rule in VASTU_RULES.items()
    )
    score = round(matched_weight / assessed_weight * 100) if assessed_weight else None
    return {
        'plot_length': length,
        'plot_width': width,
        'plot_shape': plot_shape,
        'plot_area': round(length * width, 2),
        'north_direction': north_direction,
        'north_label': DIRECTION_LABELS[north_direction],
        'score': score,
        'matched_count': matched,
        'needs_review_count': needs_review,
        'missing_count': missing,
        'assessed_count': matched + needs_review,
        'total_rules': len(VASTU_RULES),
        'coverage_percent': round(assessed_weight / total_weight * 100) if total_weight else 0,
        'matched_weight': round(matched_weight, 2),
        'assessed_weight': round(assessed_weight, 2),
        'total_weight': round(total_weight, 2),
        'calculation_method': (
            'Weighted match percentage: sum of matched guideline weights divided by the weights '
            'of rules with a valid direction, multiplied by 100. Missing directions are excluded '
            'from the score and reported separately. Preferred directions and weights can be '
            'configured in this analysis; defaults are maintained in vastu_engine.py.'
        ),
        'rules': results,
        'layout_directions': layout_directions,
        'disclaimer': (
            'Vastu guidance is a traditional cultural practice, not a scientifically proven prediction. '
            'This score does not predict health, wealth, luck, or construction safety.'
        ),
    }
