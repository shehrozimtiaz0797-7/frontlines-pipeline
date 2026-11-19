"""Original FrontLines Maps music: slow Ottoman war march (Hijaz scale, deep davul, choir, reed).
Chosen by the channel owner on 19 Nov 2026 (no snare clicks). python styles.py ottoman_slow out.wav seconds"""
import sys, wave, numpy as np
style, out, dur = sys.argv[1], sys.argv[2], float(sys.argv[3])
SR = 32000; N = int(dur*SR)+SR; t = np.arange(N)/SR
rng = np.random.default_rng(7)
L = np.zeros(N); R = np.zeros(N)
def add(s, st, pan=0.5, g=1.0):
    i = int(st*SR); n = min(len(s), N-i)
    if n > 0: L[i:i+n] += s[:n]*g*(1-pan); R[i:i+n] += s[:n]*g*pan
def env(n, a, r):
    e = np.ones(n); A, B = int(a*SR), int(r*SR)
    if A: e[:A] = np.linspace(0, 1, A)
    if B: e[-B:] *= np.linspace(1, 0, B)
    return e
F = lambda base, st: base*2**(st/12)
def pad(fr, ln, bright=0.4):
    n = int(ln*SR); u = np.arange(n)/SR
    s = sum(np.sin(2*np.pi*fr*(1+d)*u) for d in (-0.005, 0, 0.006)) + bright*np.sin(2*np.pi*fr*2*u)
    return s*env(n, ln*0.3, ln*0.3)
def choir(fr, ln):
    n = int(ln*SR); u = np.arange(n)/SR; s = np.zeros(n)
    for k in range(1, 20):
        h = fr*k; w = np.exp(-((h-700)/180)**2) + 0.7*np.exp(-((h-1150)/200)**2) + 0.25*np.exp(-((h-2600)/300)**2) + 0.3/k
        for d in (-0.006, 0.0, 0.007):
            s += w*np.sin(2*np.pi*h*(1+d)*u + rng.uniform(0, 6))
    return s*env(n, ln*0.35, ln*0.35)
def reed(fr, ln):
    n = int(ln*SR); u = np.arange(n)/SR
    ph = 2*np.pi*fr*np.cumsum(1+0.006*np.sin(2*np.pi*5.5*u)*np.minimum(1, u/0.25))/SR
    return (np.sin(ph)+0.5*np.sin(2*ph)+0.35*np.sin(3*ph)+0.15*np.sin(5*ph))*env(n, 0.05, min(0.25, ln/2))
def drum(low=50, decay=5, g=1.0, noise=0.5):
    n = int(1.2*SR); u = np.arange(n)/SR
    return (np.sin(2*np.pi*(low+60*np.exp(-u*25))*u)*np.exp(-u*decay) + rng.normal(0, 1, n)*np.exp(-u*40)*noise)*g
def cym(g=1.0):
    n = int(3*SR); u = np.arange(n)/SR
    return np.diff(np.concatenate([[0], rng.normal(0, 1, n)]))*np.exp(-u*1.5)*g
prog = lambda sec: 0.35 if sec < 0.15 else (0.7 if sec < 0.5 else 1.0)

beat = 60/76; D = 146.83; H = [0,1,4,5,7,8,10,12,13,16]
roots = [0, 1, 0, -2]
mel = [[(4,1),(5,1),(7,2)], [(8,1),(7,0.5),(5,0.5),(4,2)], [(7,1),(8,1),(10,1),(8,1)], [(5,1),(4,1),(1,1),(0,1)]]
for b in range(int(dur/(4*beat))+1):
    t0 = b*4*beat; p = prog(t0/dur); r = roots[b % 4]
    add(choir(F(D, r-12), 4*beat+0.6), t0, 0.5, 0.012)
    add(pad(F(D, r-24), 4*beat+0.6), t0, 0.5, 0.12)
    for pos, g in ((0,1),(2,0.9),(3,0.55)):
        add(drum(45, 4, g, 0.08), t0+pos*beat, 0.5, 0.45*p)
    if b >= 2:
        tt = t0
        for d, ln in mel[b % 4]:
            add(reed(F(D, H[d % 10] + 12*(d // 10)), ln*beat*0.97), tt, 0.55, 0.10)
            tt += ln*beat
    if b % 4 == 0: add(cym(), t0, 0.5, 0.05*p)
def verb(x):
    y = x.copy()
    for d, g in ((0.031,0.35),(0.041,0.3),(0.059,0.25),(0.083,0.2),(0.127,0.15),(0.181,0.1)):
        k = int(d*SR); y[k:] += x[:-k]*g
    return y
L, R = verb(L), verb(R)
fade = np.minimum(1, t/1.5)*np.clip((dur-t)/3, 0, 1)
st = np.stack([L*fade, R*fade], 1); st = np.tanh(st/(np.abs(st).max()*0.6))*0.9
with wave.open(out, 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((st*32767).astype(np.int16).tobytes())
