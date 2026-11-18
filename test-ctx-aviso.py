#!/usr/bin/env python3
"""Banco de ctx-aviso (sintético, sin datos reales)."""
import json, os, subprocess, sys, tempfile, time
H = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ctx-aviso.py")
T = tempfile.mkdtemp(); fallos = 0
def tr(nombre, ctxs, extra=()):
    p = os.path.join(T, nombre)
    with open(p, "w") as f:
        for c in ctxs:
            f.write(json.dumps({"type": "assistant", "message": {"usage": {"input_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": c - 1}}}) + "\n")
        for e in extra: f.write(e + "\n")
    return p
def run(sid, p, cwd="/srv/proyecto-a/x", entrada=None):
    inp = entrada if entrada is not None else json.dumps({"session_id": sid, "transcript_path": p, "cwd": cwd})
    r = subprocess.run([sys.executable, H], input=inp, capture_output=True, text=True, env={**os.environ, "CTX_AVISO_DIR": os.path.join(T, "m")})
    return r.returncode, r.stdout
def chk(n, cond, det=""):
    global fallos
    print(("ok  " if cond else "FALLA"), n, det)
    if not cond: fallos += 1
rc, o = run("a", tr("a1", [60000, 150000, 199000])); chk("<200k no avisa", rc == 0 and o == "")
rc, o = run("b", tr("b1", [60000, 210000])); chk("210k avisa nivel 200k", rc == 0 and "200k" in o and "systemMessage" in o and "additionalContext" in o)
rc, o = run("b", tr("b1", [60000, 220000])); chk("segundo prompt a 220k NO repite", o == "")
rc, o = run("b", tr("b2", [60000, 310000])); chk("310k avisa nivel 300k", "300k" in o)
rc, o = run("b", tr("b2", [60000, 320000])); chk("300k no se repite", o == "")
rc, o = run("c", tr("c1", [60000, 350000])); chk("salto directo a 350k: un solo aviso (300k)", o.count("systemMessage") == 1 and "300k" in o)
rc, o = run("c", tr("c1", [60000, 350000])); chk("y no repite el de 200k después", o == "")
rc, o = run("b", tr("b3", [60000, 90000])); chk("tras compactar (<150k) se rearma, sin aviso", o == "")
rc, o = run("b", tr("b4", [60000, 230000])); chk("rearmado: vuelve a avisar a 230k", "200k" in o)
rc, o = run("d", tr("d1", [400000]), cwd="/srv/otro/x"); chk("fuera de las rutas: no avisa", o == "" and rc == 0)
rc, o = run("e", tr("e1", [400000]), cwd="/srv/proyecto-b/w"); chk("ruta configurada: avisa", "300k" in o)
for malo in ("/srvx", "/srv/otro/x", "/srv/otra", "/", "/root"):
    rc, o = run("r3", tr("r3a", [400000]), cwd=malo); chk("%s no avisa" % malo, o == "" and rc == 0)
rc, o = run("f", "/no/existe"); chk("transcript inexistente: silencio, rc 0", rc == 0 and o == "")
rc, o = run("g", None, entrada="esto no es json"); chk("entrada rota: silencio, rc 0", rc == 0 and o == "")
rc, o = run("h", tr("h1", [60000], extra=["{roto", '{"type":"assistant","isSidechain":true,"message":{"usage":{"input_tokens":900000}}}']))
chk("ignora líneas rotas y subagentes (sidechain)", rc == 0 and o == "")
grande = tr("g1", [60000] * 20000 + [250000])
t0 = time.time(); rc, o = run("i", grande); dt = time.time() - t0
chk("transcript de ~4 MB: avisa y tarda <0,5 s", "200k" in o and dt < 0.5, f"{dt:.2f}s")
# --- 9-nov: PostToolUse ---
def run_ev(sid, p, ev):
    inp = json.dumps({"session_id": sid, "transcript_path": p, "cwd": "/srv/proyecto-a/x", "hook_event_name": ev})
    return run(sid, p, entrada=inp)
rc, o = run_ev("pt1", tr("pt1", [60000, 215000]), "PostToolUse"); chk("PostToolUse a 215k avisa con su evento", rc == 0 and '"hookEventName": "PostToolUse"' in o and "compacta" in o)
rc, o = run_ev("pt1", tr("pt1", [60000, 216000]), "UserPromptSubmit"); chk("tras avisar en PostToolUse, el prompt NO repite", o == "")
rc, o = run_ev("pt2", tr("pt2", [60000, 215000]), "UserPromptSubmit"); chk("UserPromptSubmit sigue con su evento", '"hookEventName": "UserPromptSubmit"' in o)
rc, o = run_ev("pt3", tr("pt3", [60000, 215000]), "PreToolUse"); chk("evento desconocido cae a UserPromptSubmit (no rompe)", rc == 0 and '"hookEventName": "UserPromptSubmit"' in o)
rc, o = run_ev("pt4", tr("pt4", [60000, 150000]), "PostToolUse"); chk("PostToolUse <200k silencio", o == "")
print("FALLOS:", fallos); sys.exit(1 if fallos else 0)
