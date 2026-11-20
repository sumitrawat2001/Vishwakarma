import re

from vastu_engine import DIRECTION_LABELS, STANDARD_RULE_LIBRARY


_ROOM_ALIASES = (
    ('main_entrance', ('main entrance', 'entrance', 'front door', 'door', 'darwaza', 'pravesh', 'मुख्य द्वार', 'दरवाज़ा', 'प्रवेश')),
    ('kitchen', ('kitchen', 'rasoi', 'रसोई', 'किचन')),
    ('master_bedroom', ('master bedroom', 'bedroom', 'bed room', 'sone ka kamra', 'शयनकक्ष', 'बेडरूम')),
    ('living_room', ('living room', 'living area', 'hall', 'बैठक', 'लिविंग रूम')),
    ('pooja_room', ('pooja room', 'puja room', 'pooja', 'puja', 'prayer room', 'पूजा घर', 'पूजा कक्ष')),
    ('bathroom_toilet', ('bathroom', 'toilet', 'washroom', 'restroom', 'bath', 'shauchalay', 'शौचालय', 'बाथरूम')),
    ('staircase', ('staircase', 'stairs', 'stair', 'seedhi', 'सीढ़ी', 'सीढ़ियां')),
    ('overhead_water_tank', ('overhead water tank', 'water tank', 'tank', 'पानी की टंकी')),
    ('underground_water_source', ('underground water source', 'borewell', 'bore well', 'underground water', 'बोरवेल', 'कुआं')),
)

_ROMAN_HINDI_WORDS = {
    'batao', 'bataye', 'kaise', 'kahan', 'kya', 'meri', 'mera', 'ghar',
    'mein', 'ki', 'ka', 'hai', 'chahiye', 'rasoi', 'darwaza', 'sujhav',
}

_DIRECTION_HINGLISH = {
    'N': 'Uttar (North)',
    'NE': 'Uttar-Purv (Northeast)',
    'E': 'Purv (East)',
    'SE': 'Dakshin-Purv (Southeast)',
    'S': 'Dakshin (South)',
    'SW': 'Dakshin-Pashchim (Southwest)',
    'W': 'Pashchim (West)',
    'NW': 'Uttar-Pashchim (Northwest)',
}

_DIRECTION_HINDI = {
    'N': 'उत्तर',
    'NE': 'उत्तर-पूर्व',
    'E': 'पूर्व',
    'SE': 'दक्षिण-पूर्व',
    'S': 'दक्षिण',
    'SW': 'दक्षिण-पश्चिम',
    'W': 'पश्चिम',
    'NW': 'उत्तर-पश्चिम',
}

_ROOM_HINDI = {
    'main_entrance': 'मुख्य दरवाज़ा',
    'kitchen': 'रसोई',
    'master_bedroom': 'मुख्य शयनकक्ष',
    'living_room': 'बैठक',
    'pooja_room': 'पूजा कक्ष',
    'bathroom_toilet': 'स्नानघर / शौचालय',
    'staircase': 'सीढ़ियां',
    'overhead_water_tank': 'पानी की टंकी',
    'underground_water_source': 'भूमिगत जल स्रोत',
}


def _language_for(question):
    if re.search(r'[\u0900-\u097f]', question):
        return 'hi'
    words = set(re.findall(r'[a-z]+', question.lower()))
    return 'hinglish' if words & _ROMAN_HINDI_WORDS else 'en'


def _find_component(question):
    normalized = question.lower()
    return next(
        (
            component
            for component, aliases in _ROOM_ALIASES
            if any(alias in normalized for alias in aliases)
        ),
        None,
    )


def _rule_index(rules):
    indexed = {}
    for rule in rules or []:
        if not isinstance(rule, dict) or not rule.get('enabled', True):
            continue
        component = rule.get('component')
        if component:
            indexed.setdefault(component, []).append(rule)
    if rules is None:
        for component, rule in STANDARD_RULE_LIBRARY.items():
            indexed[component] = [rule]
    return indexed


def _preferred_directions(rule):
    directions = rule.get('preferred_directions')
    if not directions and rule.get('preferred'):
        directions = [rule['preferred']]
    return [direction for direction in directions or [] if direction in DIRECTION_LABELS]


def _direction(direction, language):
    if direction not in DIRECTION_LABELS:
        return ''
    if language == 'hi':
        return f"{_DIRECTION_HINDI[direction]} ({direction})"
    if language == 'hinglish':
        return f"{_DIRECTION_HINGLISH[direction]} ({direction})"
    return f"{DIRECTION_LABELS[direction]} ({direction})"


def _room_answer(component, rule_group, analysis, language):
    room_name = _ROOM_HINDI.get(component, component.replace('_', ' ')) if language == 'hi' else (
        ' '.join(word.title() for word in component.split('_'))
    )
    preferences = []
    for rule in rule_group:
        preferences.extend(_preferred_directions(rule))
    preferences = list(dict.fromkeys(preferences))
    preference_text = ', '.join(_direction(direction, language) for direction in preferences)
    if not preference_text:
        if language == 'hi':
            return f"{room_name} के लिए अभी कोई सक्रिय नियम नहीं है। Admin से नियम जाँचने को कहें।"
        if language == 'hinglish':
            return f"{room_name} ke liye abhi koi active rule nahi hai. Admin se rule check karwayein."
        return f"There is no active configured rule for the {room_name.lower()}. Ask an administrator to review the rule set."

    analysis_rules = (analysis or {}).get('analysis_details', {}).get('rules', [])
    room_results = [rule for rule in analysis_rules if rule.get('component') == component]
    actual_directions = list(dict.fromkeys(
        rule.get('actual_direction') for rule in room_results
        if rule.get('actual_direction') in DIRECTION_LABELS
    ))
    actual = ', '.join(_direction(direction, language) for direction in actual_directions)
    alternatives = list(dict.fromkeys(
        direction
        for rule in rule_group
        for direction in (rule.get('alternative_directions') or rule.get('alternatives') or [])
        if direction in DIRECTION_LABELS
    ))
    alternative_text = ', '.join(_direction(direction, language) for direction in alternatives)
    conflict = len(preferences) > 1

    if language == 'hi':
        answer = f"आपके चुने गए पारंपरिक नियम के अनुसार {room_name} के लिए {preference_text} पसंदीदा है।"
        if alternative_text:
            answer += f" वैकल्पिक दिशाएं: {alternative_text}।"
        if actual:
            answer += f" आपके सेव किए गए विश्लेषण में इसकी दिशा {actual} है।"
        if conflict:
            answer += " अलग-अलग सक्रिय नियमों में मतभेद है; अपनी परंपरा के अनुसार चुनें।"
        return answer + " यह सांस्कृतिक मार्गदर्शन है, वैज्ञानिक या सुरक्षा जाँच नहीं। हवा, पाइपलाइन, संरचना और स्थानीय नियमों को प्राथमिकता दें।"

    if language == 'hinglish':
        answer = f"Configured traditional rule ke hisaab se {room_name} ke liye {preference_text} pasandida hai."
        if alternative_text:
            answer += f" Alternative dishaen: {alternative_text}."
        if actual:
            answer += f" Aapke saved analysis mein current disha {actual} hai."
        if conflict:
            answer += " Active rules mein preference ka matbhed hai; apni parampara ke hisaab se chunen."
        return answer + " Ye sanskritik margdarshan hai, scientific ya safety check nahi. Hawa, plumbing, structure aur local rules ko pehle dekhein."

    answer = f"The configured traditional rule prefers {preference_text} for the {room_name.lower()}."
    if alternative_text:
        answer += f" Alternatives listed by the configured rules: {alternative_text}."
    if actual:
        answer += f" Your saved analysis places it in {actual}."
    if conflict:
        answer += " Active rules have different preferences, so choose the tradition you want to follow."
    return answer + " This is cultural guidance, not a scientific or safety assessment. Prioritize ventilation, plumbing, structural safety, and local requirements."


def answer_vastu_question(question, rules=None, project=None, analysis=None):
    """Answer a Vastu question using configured rules and optional saved project context."""
    language = _language_for(question)
    normalized = question.lower()
    component = _find_component(normalized)
    if component:
        return _room_answer(component, _rule_index(rules).get(component, []), analysis, language)

    details = (analysis or {}).get('analysis_details') or {}
    score = details.get('score', (analysis or {}).get('score'))
    if any(word in normalized for word in ('score', 'scoring', 'ank', 'प्रतिशत', 'स्कोर')):
        if score is None:
            if language == 'hi':
                return 'अभी कोई स्कोर उपलब्ध नहीं है। पहले घर की दिशा और कमरों की जानकारी देकर विश्लेषण चलाएं। यह स्कोर केवल चुने गए पारंपरिक नियमों की तुलना है।'
            if language == 'hinglish':
                return 'Abhi score nahi hai. Pehle ghar ki disha aur room details dekar analysis chalayein. Score sirf chune hue traditional rules ka comparison hai.'
            return 'There is no saved score yet. Enter the house orientation and room directions, then run an analysis. The score only compares the selected traditional rules.'
        if language == 'hi':
            return f"आपके सेव किए गए विश्लेषण का संकेतात्मक स्कोर {score}/100 है। यह केवल सक्रिय नियमों और उपलब्ध दिशाओं की तुलना है; इसे घर की गुणवत्ता, भाग्य या सुरक्षा का माप न मानें।"
        if language == 'hinglish':
            return f"Aapke saved analysis ka indicative score {score}/100 hai. Ye sirf active rules aur available directions ka comparison hai, ghar ki quality, kismat ya safety ka measure nahi."
        return f"Your saved analysis has an indicative score of {score}/100. It compares active rules with available directions; it is not a measure of house quality, fortune, or safety."

    if any(word in normalized for word in ('improve', 'recommend', 'suggest', 'sujhav', 'sudhar', 'बेहतर', 'सुधार', 'सलाह')):
        review_rules = [
            item for item in details.get('rules', [])
            if item.get('status') in {'differs', 'partial', 'insufficient'}
        ]
        if review_rules:
            items = review_rules[:3]
            if language == 'hi':
                return 'आपके विश्लेषण में देखने योग्य बातें: ' + '; '.join(
                    f"{item.get('component_label')}: {item.get('explanation')}" for item in items
                ) + '। बदलाव ज़रूरी नहीं; जगह बदलना संभव न हो तो सुरक्षा, हवा और स्थानीय नियम पहले रखें।'
            return 'Items to review in your saved analysis: ' + '; '.join(
                f"{item.get('component_label')}: {item.get('explanation')}" for item in items
            ) + '. Changes are optional; prioritize safety, ventilation, and local requirements if relocation is not practical.'

    if any(word in normalized for word in ('plot', 'area', 'dimension', 'north', 'orientation', 'प्लॉट', 'उत्तर दिशा')):
        if project:
            size = f"{project.get('plot_length')} × {project.get('plot_width')} {project.get('unit', 'ft')}"
            if language == 'hi':
                return f"चुने गए प्रोजेक्ट का प्लॉट {size} है। दिशा का सही मिलान करने के लिए योजना में North/उत्तर की दिशा तय करें और कमरों की जगह जाँचें।"
            return f"The selected project plot is {size}. Set the plan's north orientation and confirm room positions before interpreting directions."

    if language == 'hi':
        return 'मैं रसोई, मुख्य दरवाज़े, शयनकक्ष, बैठक, पूजा कक्ष, स्नानघर, सीढ़ियों और पानी की टंकी के बारे में चुने गए पारंपरिक नियम समझा सकता हूं। किसी कमरे का नाम पूछें। ये नियम वैज्ञानिक या सुरक्षा प्रमाण नहीं हैं।'
    if language == 'hinglish':
        return 'Main kitchen, main entrance, bedroom, living room, pooja room, bathroom, staircase aur water tank ke configured traditional rules samjha sakta hoon. Kisi room ka naam poochhein. Ye rules scientific ya safety proof nahi hain.'
    return 'I can explain the configured traditional rules for the kitchen, entrance, bedroom, living room, prayer room, bathroom, staircase, and water placement. Ask about a room. These preferences are not scientific or safety guidance.'
