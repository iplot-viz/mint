import dataclasses
import json
from json import JSONEncoder
from typing import Dict, List, get_args


class JSONExporter:

    def to_json(self, obj):
        return json.dumps(obj, cls=DataclassJSONEncoder, indent=4)

    def from_json(self, string):
        return self.dataclass_from_dict(json.loads(string))


    def dataclass_from_dict(self,d, klass=None):
        print("D_F_D",d,klass)
        """
        Creates a dataclass instance from nested dicts. If dict has a _type key then this value
        is used as a dataclass base class
        :param d:
        :param klass:
        :return:
        """

        def create_klass(kls: str):
            parts = kls.split('.')
            m = __import__(".".join(parts[:-1]))
            for comp in parts[1:]:
                m = getattr(m, comp)
            return m

        if isinstance(d, Dict):
            if d.get("_type") is not None:
                klass = create_klass(d.get("_type"))
            else:
                return {k: self.dataclass_from_dict(v) for (k, v) in d.items()}

        if isinstance(d, List):
            return [self.dataclass_from_dict(e) for e in d]

        try:
            field_types = {f.name: f.type for f in dataclasses.fields(klass)}
            return klass(**{f: self.dataclass_from_dict(d[f], field_types[f]) for f in d})
        except:
            return d


class DataclassJSONEncoder(JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)
