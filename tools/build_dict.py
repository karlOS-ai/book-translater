#!/usr/bin/env python3
"""Builds the offline dictionary shards in docs/dict/ from the Ding English–German dictionary.

Ding (https://dict.tu-chemnitz.de/, GPL-2+, Frank Richter) is available on Ubuntu/Debian as
the package `trans-de-en` (file /usr/share/trans/de-en):

    apt-get download trans-de-en && dpkg-deb -x trans-de-en_*.deb x
    python3 tools/build_dict.py x/usr/share/trans/de-en

Output: docs/dict/en-<xx>.json and docs/dict/de-<xx>.json, sharded by the first letters (see shard_of),
so the app only loads the slice it needs. Each shard maps a lower-case lookup key to either
  {"l": "<base form>"}                          an inflected form (glimpsed → glimpse), or
  {"s": [[pos, translation, source], ...],      senses, best first; translation is a "; " list
   "p": [[source phrase, translation], ...]}    phrases and idioms that contain the word.
"""
import gzip, json, os, re, sys
from collections import defaultdict
from functools import lru_cache

try:
    from wordfreq import zipf_frequency  # pip install wordfreq — ranks everyday senses first
except ImportError:
    zipf_frequency = None

SRC = sys.argv[1] if len(sys.argv) > 1 else '/usr/share/trans/de-en'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'docs', 'dict')

POS = {'m': 'Substantiv', 'f': 'Substantiv', 'n': 'Substantiv', 'pl': 'Substantiv', 'adj': 'Adjektiv', 'adv': 'Adverb',
       'vt': 'Verb', 'vi': 'Verb', 'vr': 'Verb', 'v': 'Verb', 'prp': 'Präposition', 'conj': 'Konjunktion', 'pron': 'Pronomen',
       'interj': 'Interjektion', 'num': 'Zahlwort', 'art': 'Artikel', 'ppron': 'Pronomen', 'adj; adv': 'Adjektiv'}
ARTICLE = {'m': 'der', 'f': 'die', 'n': 'das', 'pl': 'die'}
# subject tags that mark a specialised sense; such senses are ranked after everyday ones
COMMON_TAGS = {'ugs.', 'übtr.', 'geh.', 'Br.', 'Am.', 'coll.', 'fig.', 'formal', 'humor.', 'poet.', 'Dt.', 'Sc.', 'adm.', 'iron.', 'neg.',
               # everyday subject areas a novel is full of (body, animals, plants, food, clothes …)
               'anat.', 'zool.', 'bot.', 'cook.', 'ornith.', 'textil.', 'sport', 'mus.', 'geogr.', 'relig.', 'art', 'lit.', 'agr.',
               'meteo.', 'psych.', 'pol.', 'soc.', 'hist.', 'mil.', 'arch.', 'educ.', 'transp.', 'auto', 'naut.', 'aviat.', 'school', 'envir.'}
# slang, dated, rare and regional senses go to the very end
RARE_TAGS = {'slang', 'Slang', 'vulg.', 'pej.', 'veraltet', 'obs.', 'selten', 'rare', 'euphem.', 'kindersprachlich', 'Jugendsprache',
             'Ös.', 'Schw.', 'Bayr.', 'Süddt.', 'Norddt.', 'Mitteldt.', 'Westdt.', 'Ostdt.', 'Südtirol', 'BW', 'Austr.', 'NZ', 'Can.', 'Ir.', 'dialect', 'archaic', 'old use'}
PREPS = {'vor', 'an', 'auf', 'mit', 'with', 'at', 'to', 'for', 'of', 'in', 'on', 'über', 'um', 'zu', 'für', 'von', 'aus', 'bei', 'nach', 'gegen', 'from', 'into', 'about', 'by', 'sth.', 'sb.', 'jdn.', 'jdm.', 'etw.'}


def context_penalty(text):
    """A sense narrowed by a note in brackets ('(Wind) rauschen', 'pale (of a fence)') is not the main meaning."""
    return 0.5 if any(c.strip().lower() not in PREPS for c in re.findall(r'\(([^)]*)\)', text)) else 0
PH = r"(?:sb|sth|jdn|jdm|jds|etw|jd)\.(?:'s)?"
PLACEHOLDER = re.compile(r"(?<![\w.])" + PH + r"(?:/" + PH + r")*(?![\w])|\b(?:one's|oneself|someone|something|sich)\b")


def split_top(s, sep):
    """Split on sep outside of (), [], {}."""
    out, depth, cur, i = [], 0, [], 0
    while i < len(s):
        c = s[i]
        if c in '([{': depth += 1
        elif c in ')]}': depth = max(0, depth - 1)
        if depth == 0 and s.startswith(sep, i):
            out.append(''.join(cur)); cur = []; i += len(sep); continue
        cur.append(c); i += 1
    out.append(''.join(cur))
    return [x.strip() for x in out]


def tags_of(s):
    return re.findall(r'\{([^}]*)\}', s), re.findall(r'\[([^\]]*)\]', s)


def clean(s):
    s = re.sub(r'\{[^}]*\}|\[[^\]]*\]|\([^)]*\)|<[^>]*>', ' ', s)
    s = s.replace('/', ' / ') if False else s
    return re.sub(r'\s+', ' ', s).strip(' ,;:')


def key_of(s, verb=False):
    s = clean(s).lower().replace('’', "'")
    if s.startswith('to ') and len(s) > 3: s = s[3:]
    return s


def keys_for(s):
    """Lookup keys for one source-language synonym: without sb./sth. placeholders first, then as written."""
    k = key_of(s)
    k2 = re.sub(r'\s+', ' ', PLACEHOLDER.sub(' ', k)).strip()
    out = list(dict.fromkeys(x for x in (k2, k) if x))
    return [x for x in out if len(x) <= 48 and len(x.split()) <= 5 and re.search(r'[a-zäöüß]', x)]


def de_display(syn):
    """German term for display: 'Ausrede {f}' → 'die Ausrede'; tags and notes removed."""
    t, _ = tags_of(syn)
    base = clean(syn)
    if not base: return ''
    g = next((x for x in t if x in ARTICLE), None)
    if g and ' ' not in base and base[:1].isupper():
        return f'{ARTICLE[g]} {base}' + (' (Pl.)' if g == 'pl' else '')
    return base


def en_display(syn):
    return clean(syn)


def pos_of(*parts):
    for p in parts:
        for t in tags_of(p)[0]:
            t = t.strip()
            if t in POS: return POS[t]
            if t.startswith('v'): return 'Verb'
    return ''


def tag_level(text):
    """0 for everyday senses, 1 for subject areas ([med.], [techn.] …), 2 for slang/dated/regional."""
    level = 0
    for t in tags_of(text)[1]:
        for x in t.split(';'):
            x = x.strip()
            if x in RARE_TAGS: return 2
            if x and x not in COMMON_TAGS: level = 1
    return level


def specialised(target_part, source_syn):
    """Level of one sense: the source synonym's own tags, plus the target side's tags when they hold for
    all of its synonyms (a regional tag on just one German synonym does not make the sense rare)."""
    tgt = [tag_level(x) for x in split_top(target_part, '; ')] or [0]
    return max(tag_level(source_syn), min(tgt))


@lru_cache(maxsize=None)
def zipf(term, lang):
    if not zipf_frequency: return 0.0
    t = re.sub(r'^(der|die|das) ', '', PLACEHOLDER.sub(' ', term)).replace('(Pl.)', '').strip()
    return zipf_frequency(t, lang) if t else 0.0


PRONOUN_FORM = re.compile(r"^(?:(?:I|you|he|she|it|we|they|ich|du|er|sie|es|wir|ihr)(?:/\w+)*\s+)+(?:has/had\s+|have/had\s+|ist/war\s+|hat/hatte\s+)?")
JUNK_PHRASE = re.compile(r"(^|\s)(I|he|she|it|we|they|ich|er|sie|es|wir)(/|\s+(would|has|had|is|was|würde|hat|hatte|ist|war)\b)|^(more|most|am)\s|;")


def inflections(part):
    """Single-word forms in a sub-entry: 'he/she runs' → runs, 'I/he/she ran' → ran."""
    out = []
    for form in split_top(part, '; '):
        f = PRONOUN_FORM.sub('', clean(form)).strip().lower()
        if f and ' ' not in f and f.isalpha(): out.append(f)
    return out


def build(direction):
    """direction 'en': English → German; 'de': German → English."""
    senses = defaultdict(list)   # key -> [(score, pos, translation, source)]
    phrases = defaultdict(list)  # key -> [(len, source phrase, translation)]
    forms = {}                   # inflected form -> base form
    with open(SRC, encoding='utf-8') as f:
        for ln, line in enumerate(f):
            if line.startswith('#') or ' :: ' not in line: continue
            de, en = line.rstrip('\n').split(' :: ', 1)
            dparts, eparts = split_top(de, ' | '), split_top(en, ' | ')
            nparts = len(dparts)
            if len(dparts) != len(eparts): dparts, eparts = dparts[:1], eparts[:1]
            src_parts, tgt_parts = (eparts, dparts) if direction == 'en' else (dparts, eparts)
            pos = pos_of(dparts[0], eparts[0])
            head_syns = split_top(src_parts[0], '; ')
            tgt_syns = [x for x in (de_display(s) if direction == 'en' else en_display(s) for s in split_top(tgt_parts[0], '; ')) if x]
            if not tgt_syns: continue
            translation = '; '.join(dict.fromkeys(tgt_syns))
            head_keys = set()
            lang = 'de' if direction == 'en' else 'en'
            richness = min(nparts, 12) * 0.12
            context = context_penalty(dparts[0]) + 0.5 * bool(re.search(r'\[(übtr|fig)\.\]', dparts[0]))
            common = zipf(tgt_syns[0], lang) * 0.35
            for i, syn in enumerate(head_syns):
                for k in keys_for(syn):
                    head_keys.add(k)
                    own = context_penalty(syn) + 0.5 * bool(re.search(r'\[(fig|übtr)\.\]', syn))
                    only = 0.4 if len(head_syns) == 1 else 0
                    spec = specialised(tgt_parts[0], syn)
                    score = spec * 1.2 + context + own + min(i, 3) * 0.7 - richness - common - only + ln / 1e8
                    senses[k].append((score, pos, translation, clean(syn)))
            # inflected forms: irregular forms in braces (to run {ran; run}) and the sub-entries
            # (to glimpse | glimpsing | glimpsed …, he/she runs, I/he/she ran; plurals: mouse | mice)
            base = keys_for(head_syns[0])[0] if head_syns and keys_for(head_syns[0]) else ''
            if base and ' ' not in base and base.isalpha():
                if direction == 'en':
                    for br in re.findall(r'\{([^}]*)\}', head_syns[0]):
                        for fk in (x.strip().lower() for x in br.split(';')):
                            if fk.isalpha() and fk != base and fk not in POS: forms.setdefault(fk, base)
                for p in src_parts[1:8]:
                    for fk in inflections(p):
                        if fk != base and fk[0] == base[0] and len(fk) <= len(base) + 5: forms.setdefault(fk, base)
            # phrases: later sub-entries that are idioms/examples using the head word
            for sp, tp in list(zip(src_parts, tgt_parts))[1:]:
                s_txt, t_txt = clean(sp), clean(tp)
                if not s_txt or not t_txt or len(s_txt.split()) < 2 or len(s_txt) > 90 or JUNK_PHRASE.search(s_txt) or JUNK_PHRASE.search(t_txt): continue
                for k in head_keys:
                    if ' ' not in k and re.search(r'\b' + re.escape(k) + r'\b', s_txt.lower()):
                        phrases[k].append((len(s_txt), s_txt, t_txt))
    out = defaultdict(dict)
    for k, lst in senses.items():
        lst.sort()
        seen, best = set(), []
        for score, pos, tr, src in lst:
            first = tr.split('; ')[0]
            if tr in seen or first in seen: continue
            seen.add(tr); seen.add(first); best.append([pos, tr, src])
            if len(best) == 8: break
        e = {'s': best}
        ph = sorted(set(phrases.get(k, [])))[:5]
        if ph: e['p'] = [[a, b] for _, a, b in ph]
        out[shard_of(k)][k] = e
    # a word only listed in the plural in Ding (oaks → Eichen) borrows the plural's senses
    for k, e in list((k, e) for sh in out.values() for k, e in sh.items()):
        if 's' in e and len(e['s']) < 3 and ' ' not in k:
            for pk in (k + 's', k + 'es'):
                pe = out.get(shard_of(pk), {}).get(pk)
                if pe and 's' in pe:
                    have = {x[1] for x in e['s']}
                    e['s'] += [x for x in pe['s'] if x[1] not in have][:3]
                    break
    for fk, base in forms.items():
        if fk not in senses and base in senses:
            out[shard_of(fk)][fk] = {'l': base}
    return out


FOLD = {'ä': 'a', 'ö': 'o', 'ü': 'u', 'ß': 's', 'é': 'e', 'è': 'e', 'à': 'a'}


def shard_of(k):
    """First letter plus a bucket for the second letter (a–f, g–m, n–s, t–z): about 250 KB per file.
    Must match shardName() in src/app.html."""
    c = FOLD.get(k[0], k[0])
    c = c if 'a' <= c <= 'z' else '_'
    c2 = FOLD.get(k[1], k[1]) if len(k) > 1 else ''
    b = 'a' if not ('a' <= c2 <= 'z') or c2 < 'g' else 'g' if c2 < 'n' else 'n' if c2 < 't' else 't'
    return c + b


PARTICLES = {'up', 'down', 'out', 'off', 'on', 'in', 'away', 'back', 'over', 'through', 'around', 'about', 'along', 'by',
             'for', 'after', 'into', 'across', 'apart', 'ahead', 'forward', 'together', 'with'}


def write_core():
    """src/core-en.json.gz: the everyday part of the English → German index (words with a wordfreq
    Zipf value of at least 1.5, phrasal verbs and their inflected forms), slimmed down so tools/build.mjs
    can embed it in the claude.ai page. That page then needs no network to look words up."""
    en = {}
    for f in os.listdir(OUT):
        if f.startswith('en-') and f.endswith('.json'):
            with open(os.path.join(OUT, f), encoding='utf-8') as fh: en.update(json.load(fh))
    core = {}
    for k, e in en.items():
        if 's' not in e: continue
        w = k.split()
        if len(w) == 1 and zipf(k, 'en') >= 1.5: n_s, n_syn, n_p = 5, 4, 2
        elif len(w) in (2, 3) and w[1] in PARTICLES and zipf(w[0], 'en') >= 3: n_s, n_syn, n_p = 4, 3, 1
        else: continue
        o = {'s': [[pos, '; '.join(tr.split('; ')[:n_syn])] for pos, tr, *_ in e['s'][:n_s]]}
        if e.get('p'): o['p'] = e['p'][:n_p]
        core[k] = o
    for k, e in en.items():
        if 'l' in e and e['l'] in core: core[k] = {'l': e['l']}
    raw = json.dumps(core, ensure_ascii=False, separators=(',', ':')).encode()
    path = os.path.join(os.path.dirname(OUT), '..', 'src', 'core-en.json.gz')
    with open(path, 'wb') as f: f.write(gzip.compress(raw, 9, mtime=0))
    print('core', len(core), 'keys', round(os.path.getsize(path) / 1e6, 2), 'MB')


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):
        if f.endswith('.json') or f.endswith('.json.gz'): os.remove(os.path.join(OUT, f))
    total = 0
    for direction in ('en', 'de'):
        shards = build(direction)
        for s, data in sorted(shards.items()):
            raw = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()
            path = os.path.join(OUT, f'{direction}-{s}.json')
            with open(path, 'wb') as f:
                f.write(raw)
            total += len(gzip.compress(raw, 6))
        print(direction, sum(len(d) for d in shards.values()), 'keys')
    write_core()
    with open(os.path.join(OUT, 'LICENSE.txt'), 'w') as f:
        f.write('Wörterbuchdaten: Ding English–German dictionary, (c) Frank Richter, TU Chemnitz, 1995–2023.\n'
                'https://dict.tu-chemnitz.de/ — GNU General Public License, Version 2 oder später.\n')
    print('total', round(total / 1e6, 2), 'MB gzipped (served compressed by most hosts)')


if __name__ == '__main__':
    main()
