#!/usr/bin/env python3
"""Fail if the T1 build's manifest revisions or runtime inputs drift from B."""
import json, sys, pathlib
manifest=pathlib.Path(sys.argv[1]); expected=pathlib.Path(sys.argv[2])
m=json.loads(manifest.read_text()); e=json.loads(expected.read_text())
bad=[]
for k,v in e["revisions"].items():
    got=m.get("revisions",{}).get(k)
    if got!=v: bad.append(f"revision {k}: expected {v}, got {got}")
for k,v in e["runtime_inputs"].items():
    got=m.get("runtime",{}).get("inputs",{}).get(k)
    if got!=v: bad.append(f"runtime {k}: expected {v}, got {got}")
if m.get("os_profile")!=e["os_profile"]: bad.append(f"os_profile: expected {e['os_profile']}, got {m.get('os_profile')}")
if bad:
    print("T1 PIN CHECK FAIL"); [print(" -",b) for b in bad]; sys.exit(1)
print("T1 PIN CHECK PASS")
