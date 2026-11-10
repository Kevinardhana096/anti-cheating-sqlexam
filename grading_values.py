"""Lossless grading values; cursor-local codecs leave application previews unchanged."""
from dataclasses import dataclass
from decimal import Decimal
import json
import re
from psycopg2 import extensions


@dataclass(frozen=True)
class JsonValue:
    value: object
    raw: str
    def __str__(self):
        return self.raw


@dataclass(frozen=True)
class ArrayValue:
    value: object
    bounds: tuple
    raw: str
    def __str__(self):
        return self.raw


def install(cursor):
    json_arrays={}
    for oid in (114,3802):
        def load_json(raw,cur):
            return None if raw is None else JsonValue(json.loads(raw,parse_float=Decimal),raw)
        codec=extensions.new_type((oid,),'GRADE_JSON',load_json)
        extensions.register_type(codec,cursor)
        array_oid=199 if oid==114 else 3807
        json_arrays[array_oid]=extensions.new_array_type((array_oid,),'GRADE_JSON_ARRAY',codec)
    with cursor.connection.cursor() as metadata:
        metadata.execute("SELECT oid FROM pg_type WHERE typcategory='A' AND typnamespace='pg_catalog'::regnamespace")
        oids=[r[0] for r in metadata.fetchall()]
    for oid in oids:
        original=json_arrays.get(oid) or extensions.string_types.get(oid)
        if original is None:
            continue
        def load_array(raw,cur,original=original):
            if raw is None:
                return None
            value=original(raw,cur)
            explicit=re.findall(r'\[(-?\d+):(-?\d+)\]',raw.split('=',1)[0]) if raw.startswith('[') else []
            bounds=[]
            if explicit:
                bounds=[(int(a),int(b)) for a,b in explicit]
            else:
                level=value
                while isinstance(level,list) and level:
                    bounds.append((1,len(level)))
                    level=level[0]
            return ArrayValue(value,tuple(bounds),raw)
        extensions.register_type(extensions.new_type((oid,),'GRADE_ARRAY',load_array),cursor)
