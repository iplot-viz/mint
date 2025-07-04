import copy
import importlib
import json
import pandas as pd
import pkgutil
import typing

from iplotProcessing.core import Signal

from iplotLogging import setupLogger

logger = setupLogger.get_logger(__name__)

DEFAULT_BLUEPRINT = json.loads(pkgutil.get_data('mint.data', 'blueprint.json'))


def parse_raw_blueprint(blueprint: dict) -> dict:
    blueprint_out = dict(blueprint)
    for k, v in blueprint_out.items():
        if k.startswith('$'):
            continue
        if v.get('type_name'):
            type_name = v.get('type_name')
            parts = type_name.split('.')
            try:
                type_func = getattr(importlib.import_module('.'.join(parts[:-1])), parts[-1])
            except ValueError:
                type_func = getattr(importlib.import_module("builtins"), type_name)
            assert callable(type_func)
            v.update({'type': type_func})
            logger.debug(f"Updated {k}.type = {type_func}")
    return blueprint_out


def remove_type_info(blueprint: dict) -> dict:
    blueprint_out = copy.deepcopy(blueprint)
    for k, v in blueprint_out.items():
        if k.startswith('$'):
            continue
        if v.get('type'):
            v.pop('type')
    return blueprint_out


def get_column_names(blueprint: dict) -> typing.Iterator[str]:
    for k, v in blueprint.items():
        if k.startswith('$'):
            continue
        if not v.get('no_export'):
            yield get_column_name(blueprint, k)


def get_column_name(blueprint: dict, key: str) -> str:
    if key.startswith('$'):
        return key
    return blueprint.get(key).get('label') or key


def get_keys_with_override(blueprint: dict) -> typing.Iterator[str]:
    for k, v in blueprint.items():
        if k.startswith('$'):
            continue
        if v.get('override'):
            yield k


def get_keys_with_export(blueprint: dict) -> typing.Iterator[str]:
    for k, v in blueprint.items():
        if k.startswith('$'):
            continue
        if v.get('export'):
            yield k


def get_code_names(blueprint: dict, predicate_keys=None):
    if predicate_keys is None:
        predicate_keys = ['no_construct']

    for k, v in blueprint.items():
        if k.startswith('$'):
            continue
        for pred in predicate_keys:
            if len(pred) and v.get(pred):
                yield v.get('code_name')
                break
        else:
            yield v.get('code_name')


def construct_signal(blueprint: dict, signal_class: type, **signal_params) -> Signal:
    for k, v in blueprint.items():
        if k.startswith('$'):
            continue
        if v.get('no_construct'):
            try:
                signal_params.pop(v.get('code_name'))
            except KeyError:
                continue
    # Remove any extra keys not expected by the signal class, like 'comment'
    signal_params.pop('comment', None)
    return signal_class(**signal_params)


def construct_params_from_signal(blueprint: dict, sig: Signal) -> dict:
    params = {}
    for k, v in blueprint.items():
        if k.startswith('$'):
            continue
        cname = v.get('code_name')
        try:
            value = getattr(sig, cname)
            params.update({cname: value})
        except AttributeError:
            logger.debug(f"Ignoring {v}")
            continue
    return params


def construct_params_from_series(blueprint: dict, row: pd.Series) -> dict:
    params = {}
    for k, v in blueprint.items():
        if k.startswith('$'):
            continue
        column_name = v.get('label') or k
        code_name = v.get('code_name')
        try:
            params.update({code_name: row[column_name]})
        except KeyError:
            logger.debug(f"Ignoring {k}, {v}")
            continue
    return params


def adjust_dataframe(blueprint: dict, df: pd.DataFrame):
    for col_name in get_column_names(blueprint):
        if col_name not in df.columns:
            df[col_name] = [''] * df.count(1).index.size
