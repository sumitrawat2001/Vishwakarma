"""Shared validation and persistence for construction management resources."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path


class ResourceValidationError(ValueError):
    """Raised when a resource payload violates its schema."""


RESOURCE_SCHEMAS = {
    'labour': {
        'required': ('name', 'role', 'rate'),
        'strings': ('name', 'role', 'unit'),
        'numbers': ('rate', 'quantity'),
        'defaults': {'unit': 'day', 'quantity': 1},
    },
    'materials': {
        'required': ('name', 'unit', 'unit_cost'),
        'strings': ('name', 'category', 'unit'),
        'numbers': ('unit_cost', 'quantity', 'reorder_level'),
        'defaults': {'quantity': 0, 'reorder_level': 0},
    },
    'equipment': {
        'required': ('name', 'rate'),
        'strings': ('name', 'category', 'unit'),
        'numbers': ('rate', 'quantity'),
        'defaults': {'category': 'general', 'unit': 'day', 'quantity': 1},
    },
    'tasks': {
        'required': ('title',),
        'strings': ('title', 'description', 'status', 'priority', 'assigned_to', 'due_date'),
        'enums': {'status': ('todo', 'in_progress', 'blocked', 'done'), 'priority': ('low', 'medium', 'high')},
        'defaults': {'status': 'todo', 'priority': 'medium'},
    },
    'expenses': {
        'required': ('description', 'amount'),
        'strings': ('description', 'category', 'date'),
        'numbers': ('amount',),
        'defaults': {'category': 'general', 'date': ''},
    },
    'documents': {
        'required': ('name', 'document_type'),
        'strings': ('name', 'document_type', 'url', 'notes'),
        'defaults': {'url': '', 'notes': ''},
    },
    'invoices': {
        'required': ('invoice_number', 'vendor', 'amount'),
        'strings': ('invoice_number', 'vendor', 'status', 'due_date'),
        'numbers': ('amount',),
        'enums': {'status': ('draft', 'issued', 'paid', 'overdue', 'cancelled')},
        'defaults': {'status': 'draft', 'due_date': ''},
    },
}


def _number(value, field):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ResourceValidationError(f'{field} must be a number.')
    if parsed < 0:
        raise ResourceValidationError(f'{field} cannot be negative.')
    return int(parsed) if parsed.is_integer() else parsed


def validate_resource(resource_type, payload, user_id, project_id=None):
    schema = RESOURCE_SCHEMAS.get(resource_type)
    if not schema:
        raise ResourceValidationError('Unknown resource type.')
    if not isinstance(payload, dict):
        raise ResourceValidationError('Request body must be a JSON object.')

    document = dict(schema.get('defaults', {}))
    for field in schema.get('strings', ()):
        if field in payload and payload[field] is not None:
            document[field] = str(payload[field]).strip()
    for field in schema.get('numbers', ()):
        if field in payload and payload[field] not in (None, ''):
            document[field] = _number(payload[field], field)
    for field in schema.get('enums', {}):
        if field in payload and payload[field] not in (None, ''):
            document[field] = str(payload[field]).strip().lower()

    for field in schema.get('required', ()):
        value = document.get(field)
        if value is None or value == '':
            raise ResourceValidationError(f'{field} is required.')
    for field, choices in schema.get('enums', {}).items():
        if document.get(field) not in choices:
            raise ResourceValidationError(f'{field} must be one of: {", ".join(choices)}.')

    document['user_id'] = str(user_id)
    document['resource_type'] = resource_type
    if project_id:
        document['project_id'] = str(project_id)
    now = datetime.utcnow().isoformat()
    document['updated_at'] = now
    return document


def serialize_resource(document):
    if not document:
        return None
    result = dict(document)
    if '_id' in result:
        result['id'] = str(result.pop('_id'))
    elif 'id' in result:
        result['id'] = str(result['id'])
    return result


class FileResourceRepository:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text('{}', encoding='utf-8')

    def _read(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8') or '{}')
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self, data):
        self.path.write_text(json.dumps(data, indent=2, default=str), encoding='utf-8')

    def list(self, user_id, project_id=None, resource_type=None):
        items = self._read().get(str(user_id), [])
        return [item for item in items if (not resource_type or item.get('resource_type') == resource_type) and (not project_id or str(item.get('project_id')) == str(project_id))]

    def create(self, document):
        data = self._read()
        record = dict(document)
        record['_id'] = str(uuid.uuid4())
        record['created_at'] = datetime.utcnow().isoformat()
        data.setdefault(str(document['user_id']), []).append(record)
        self._write(data)
        return record

    def get(self, user_id, resource_id, resource_type=None):
        return next((item for item in self.list(user_id, resource_type=resource_type) if str(item.get('_id')) == str(resource_id)), None)

    def update(self, user_id, resource_id, updates, resource_type=None):
        data = self._read()
        items = data.get(str(user_id), [])
        for item in items:
            if str(item.get('_id')) == str(resource_id) and (not resource_type or item.get('resource_type') == resource_type):
                item.update(updates)
                item['updated_at'] = datetime.utcnow().isoformat()
                self._write(data)
                return item
        return None

    def delete(self, user_id, resource_id, resource_type=None):
        data = self._read()
        items = data.get(str(user_id), [])
        remaining = [item for item in items if not (str(item.get('_id')) == str(resource_id) and (not resource_type or item.get('resource_type') == resource_type))]
        if len(remaining) == len(items):
            return False
        data[str(user_id)] = remaining
        self._write(data)
        return True


class MongoResourceRepository:
    def __init__(self, collection):
        self.collection = collection

    def list(self, user_id, project_id=None, resource_type=None):
        query = {'user_id': str(user_id)}
        if project_id:
            query['project_id'] = str(project_id)
        if resource_type:
            query['resource_type'] = resource_type
        return list(self.collection.find(query).sort('updated_at', -1))

    def create(self, document):
        record = dict(document)
        record['created_at'] = datetime.utcnow().isoformat()
        result = self.collection.insert_one(record)
        record['_id'] = result.inserted_id
        return record

    def get(self, user_id, resource_id, resource_type=None):
        from bson import ObjectId
        query_id = ObjectId(resource_id) if ObjectId.is_valid(str(resource_id)) else resource_id
        query = {'_id': query_id, 'user_id': str(user_id)}
        if resource_type:
            query['resource_type'] = resource_type
        return self.collection.find_one(query)

    def update(self, user_id, resource_id, updates, resource_type=None):
        from bson import ObjectId
        query_id = ObjectId(resource_id) if ObjectId.is_valid(str(resource_id)) else resource_id
        updates = dict(updates)
        updates['updated_at'] = datetime.utcnow().isoformat()
        query = {'_id': query_id, 'user_id': str(user_id)}
        if resource_type:
            query['resource_type'] = resource_type
        self.collection.update_one(query, {'$set': updates})
        return self.get(user_id, resource_id, resource_type)

    def delete(self, user_id, resource_id, resource_type=None):
        from bson import ObjectId
        query_id = ObjectId(resource_id) if ObjectId.is_valid(str(resource_id)) else resource_id
        query = {'_id': query_id, 'user_id': str(user_id)}
        if resource_type:
            query['resource_type'] = resource_type
        return self.collection.delete_one(query).deleted_count > 0
