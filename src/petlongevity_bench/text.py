from __future__ import annotations
import re

def norm(x):
    if x is None: return None
    if isinstance(x,bool): return x
    if isinstance(x,(int,float)): return x
    if isinstance(x,list): return tuple(sorted(norm(v) for v in x))
    s=str(x).strip().lower()
    s=re.sub(r"\s+"," ",s)
    return s

def token_set(s):
    if not s: return set()
    return set(re.findall(r"[a-z0-9]+",str(s).lower()))

def token_f1(a,b):
    A,B=token_set(a),token_set(b)
    if not A and not B: return 1.0
    if not A or not B: return 0.0
    inter=len(A&B)
    p=inter/len(B); r=inter/len(A)
    return 0.0 if p+r==0 else 2*p*r/(p+r)
