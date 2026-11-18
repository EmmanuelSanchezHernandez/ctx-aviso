#!/usr/bin/env python3
"""Hook UserPromptSubmit y PostToolUse (9-nov: así avisa también en turnos largos sin prompt del usuario): avisa UNA vez cuando el contexto de la sesión pasa de 200k y de 300k.

Motivo: la mayor parte del gasto de tokens está en llamadas con mucho contexto; un tope de ~200k ahorra cuota.
Solo avisa en las rutas de trabajo configuradas (CTX_AVISO_RUTAS). Solo AVISA: nunca bloquea.
Fail-open: cualquier error ⇒ sale en silencio con código 0. Lee sólo la cola del transcript (rápido) y no imprime contenido.
Se rearma si tras compactar el contexto baja de 150k.
"""
import json
import os
import sys

NIVELES = (200_000, 300_000)
REARME = 150_000
COLA = 600_000  # bytes de la cola del transcript a mirar
DIR = os.environ.get("CTX_AVISO_DIR", "/tmp/ctx-aviso")
RUTAS = tuple(os.environ.get("CTX_AVISO_RUTAS", "/proyecto-a/,/proyecto-b/").split(","))


def contexto(ruta):
    """Tokens de contexto de la última llamada del asistente (entrada + caché), o None."""
    tam = os.path.getsize(ruta)
    with open(ruta, "rb") as h:
        if tam > COLA:
            h.seek(tam - COLA)
            h.readline()  # descarta la línea cortada
        lineas = h.read().decode("utf-8", "ignore").splitlines()
    for linea in reversed(lineas):
        if '"usage"' not in linea:
            continue
        try:
            o = json.loads(linea)
        except ValueError:
            continue
        if o.get("type") != "assistant" or o.get("isSidechain"):
            continue
        u = (o.get("message") or {}).get("usage") or {}
        total = (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
        if total:
            return total
    return None


def main():
    d = json.load(sys.stdin)
    cwd = (d.get("cwd") or "") + "/"
    if not any(r in cwd for r in RUTAS):
        return
    evento = d.get("hook_event_name") if d.get("hook_event_name") in ("UserPromptSubmit", "PostToolUse") else "UserPromptSubmit"
    sid = str(d.get("session_id") or "")
    ruta = d.get("transcript_path") or ""
    if not sid or not ruta or not os.path.isfile(ruta):
        return
    ctx = contexto(ruta)
    if ctx is None:
        return
    os.makedirs(DIR, exist_ok=True)
    marcas = {n: os.path.join(DIR, f"{sid}-{n // 1000}k") for n in NIVELES}
    if ctx < REARME:
        for m in marcas.values():
            if os.path.exists(m):
                os.remove(m)
        return
    nivel = None
    for n in NIVELES:
        if ctx >= n and not os.path.exists(marcas[n]):
            nivel = n
    if nivel is None:
        return
    for n in NIVELES:  # al avisar del nivel alto, el bajo también queda dado
        if n <= nivel:
            open(marcas[n], "w").close()
    k = ctx // 1000
    if nivel == NIVELES[0]:
        msg = (f"⚠️ Contexto de la sesión: ~{k}k tokens (aviso a 200k). Cada llamada relee todo esto; es lo que más cuota gasta. "
               "Cierra la tarea en curso y compacta (/compact), o pide un resumen de estado y sigue en una sesión NUEVA.")
    else:
        msg = (f"🔴 Contexto de la sesión: ~{k}k tokens (aviso a 300k). Pasó el tope útil: pide un resumen de estado (objetivo, hecho, "
               "pendiente, ficheros), guárdalo y continúa en una sesión NUEVA, o compacta ya.")
    print(json.dumps({
        "systemMessage": msg,
        "hookSpecificOutput": {
            "hookEventName": evento,
            "additionalContext": msg + " (Aviso del hook ctx-aviso: díselo al usuario en una frase y sigue con lo que pide.)",
        },
    }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
