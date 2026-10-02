"""Checks for the independently authored Elastic 9.x practice set."""
from importlib import import_module

def module(v):
    number=v.t['number']
    return import_module('verify_f_semantic' if number<=3 else 'verify_f_esql' if number<=7 else 'verify_f_streams')

def query_check(v):
    return module(v).query_check(v)

def state_check(v):
    return module(v).state_check(v)
