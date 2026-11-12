#!/usr/bin/env python3
"""Strict fact-check of answer banks with Perplexity: wrong answers are removed (and, for Titanic, blocked
from the live Wikidata check too, e.g. Venezuela 'bordering' France only by sea).
  python3 scripts/factcheck.py titanic prompts/2026-11-13.json ...
  python3 scripts/factcheck.py abcs bestshot/abcs/cats/*.json
Resumable: checked items are marked and skipped. Needs PERPLEXITY_API_KEY (env or Claude's config)."""
import json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

def key():
    if os.environ.get("PERPLEXITY_API_KEY"): return os.environ["PERPLEXITY_API_KEY"]
    p = Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    return json.loads(p.read_text())["mcpServers"]["perplexity"]["env"]["PERPLEXITY_API_KEY"]

def ask(prompt, tries=5):
    body = json.dumps({"preset": "fast-search", "input": prompt}).encode()
    for i in range(tries):
        try:
            r = urllib.request.Request("https://api.perplexity.ai/v1/responses", data=body, headers={
                "Authorization": "Bearer " + key(), "Content-Type": "application/json", "User-Agent": "curl/8.4.0"})
            d = json.load(urllib.request.urlopen(r, timeout=240))
            return "\n".join(c.get("text", "") for o in d.get("output", []) if o.get("type") == "message" for c in o.get("content", []))
        except Exception:
            if i == tries - 1: raise
            time.sleep(15 * (i + 1))

RULES = ("Judge strictly and literally, as a careful trivia host would: 'border' means a shared LAND border (sea/maritime borders do not count); "
         "'in' a place means actually located there; a person must genuinely be known for that thing; a title must really be that kind of work "
         "and from that year if a year is given; anything fictional, made up, misspelled beyond recognition, or the wrong kind of thing is wrong. "
         "Common alternative names, former names and spellings of a correct answer are fine.")

def wrong(question, labels):
    """Indexes of labels that are not correct answers. Lists are checked in chunks of 120."""
    bad = set()
    for s in range(0, len(labels), 120):
        chunk = labels[s:s + 120]
        t = ask(f"Trivia prompt: \"{question}\"\nBelow are numbered candidate answers. {RULES}\n"
                "Reply with ONLY a JSON array of the numbers of the candidates that are NOT correct answers, e.g. [3, 17]. Reply [] if all are correct.\n\n"
                + "\n".join(f"{i + 1}. {l}" for i, l in enumerate(chunk)))
        m = re.search(r"\[[\d,\s]*\]", t)
        if not m: print("    unparsed reply, kept chunk:", question[:50], flush=True); continue
        nums = {int(x) - 1 for x in json.loads(m.group(0)) if 0 < int(x) <= len(chunk)}
        if len(chunk) >= 30 and len(nums) > len(chunk) * .5: print(f"    {len(nums)}/{len(chunk)} flagged looks unreliable, kept:", question[:50], flush=True); continue
        bad |= {s + i for i in nums}
    return bad

def keep(question, labels):
    """Second opinion on flagged answers: indexes that ARE correct under a fair reading (these are restored)."""
    if len(labels) > 100: return {s + k for s in range(0, len(labels), 100) for k in keep(question, labels[s:s + 100])}
    if not labels: return set()
    t = ask(f"Trivia prompt: \"{question}\"\nA strict checker flagged the numbered answers below as wrong. Give a careful second opinion: "
            "which of them ARE genuinely correct answers under a fair, ordinary reading of the prompt (e.g. a song an artist is famous for performing, "
            "a country sharing a land border through an overseas region)? Spelling variants count. Reply with ONLY a JSON array of the numbers that are correct, or [].\n\n"
            + "\n".join(f"{i + 1}. {l}" for i, l in enumerate(labels)))
    m = re.search(r"\[[\d,\s]*\]", t)
    return {int(x) - 1 for x in json.loads(m.group(0)) if 0 < int(x) <= len(labels)} if m else set(range(len(labels)))

def titanic(f):
    f = Path(f); j = json.loads(f.read_text()); cut = 0
    for m in j["modes"]:
        for p in m:
            if len(p) >= 7 or len(p) < 5: continue   # [q, answers, qid, body, ids, blocked ids, blocked names, checked, second-opinion]
            ans, ids = p[1].split("|"), p[4].split(",")
            try:
                bad = sorted(wrong(p[0], [a.split("/")[0] for a in ans]))
                ok = keep(p[0], [ans[i].split("/")[0] for i in bad]); bad = {b for k, b in enumerate(bad) if k not in ok}
            except Exception as e: print("  skip", p[0][:40], e, flush=True); continue
            p[1] = "|".join(a for i, a in enumerate(ans) if i not in bad); p[4] = ",".join(x for i, x in enumerate(ids) if i not in bad)
            p[5:] = [",".join(ids[i] for i in sorted(bad) if ids[i]), "|".join(ans[i].split("/")[0] for i in sorted(bad))]
            p += [1, 1]; cut += len(bad)
            if bad: print(f"  {f.stem} {p[0][:45]:45s} -{len(bad)}: {', '.join(ans[i].split('/')[0] for i in sorted(bad))[:110]}", flush=True)
            f.write_text(json.dumps(j, ensure_ascii=False, separators=(",", ":")))
    print("done", f.stem, "-", cut, flush=True)

def abcs(f):
    f = Path(f); d = json.loads(f.read_text())
    if d.get("checked"): return
    try: bad = wrong(f"Name a {d['noun']}", [a.split("#")[0].split("|")[0] for a in d["a"]])
    except Exception as e: print("  skip", f.stem, e, flush=True); return
    print(f"  {f.stem:14s} -{len(bad)}: {', '.join(d['a'][i].split('|')[0].split('#')[0] for i in sorted(bad))[:150]}", flush=True)
    d["a"] = [a for i, a in enumerate(d["a"]) if i not in bad]; d["checked"] = True
    f.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")))

def rescue(f):
    """For days checked before the second opinion existed: re-ask about removed answers and restore the good ones from git."""
    import subprocess
    f = Path(f); j = json.loads(f.read_text())
    orig = json.loads(subprocess.run(["git", "show", f"HEAD:{f.as_posix()}"], capture_output=True, text=True, check=True).stdout); back = 0
    for m, om in zip(j["modes"], orig["modes"]):
        for p, op in zip(m, om):
            if len(p) != 8 or not p[6]: continue
            gone = set(p[6].split("|")); cand = [(a, i) for a, i in zip(op[1].split("|"), op[4].split(",")) if a.split("/")[0] in gone]
            try: ok = keep(p[0], [a.split("/")[0] for a, _ in cand])
            except Exception as e: print("  skip", p[0][:40], e, flush=True); continue
            good = [cand[k] for k in sorted(ok)]; bad = [c for k, c in enumerate(cand) if k not in ok]
            if good: p[1] += "|" + "|".join(a for a, _ in good); p[4] += "," + ",".join(i for _, i in good)
            p[5] = ",".join(i for _, i in bad if i); p[6] = "|".join(a.split("/")[0] for a, _ in bad); p.append(1); back += len(good)
            if good: print(f"  {f.stem} {p[0][:45]:45s} +{len(good)} back: {', '.join(a.split('/')[0] for a, _ in good)[:100]}", flush=True)
            f.write_text(json.dumps(j, ensure_ascii=False, separators=(",", ":")))
    print("rescued", f.stem, "+", back, flush=True)

def abcs_rescue(f):
    import subprocess
    f = Path(f); d = json.loads(f.read_text())
    if not d.get("checked") or d.get("second"): return
    orig = json.loads(subprocess.run(["git", "show", f"HEAD:abcs/cats/{f.name}"], cwd=f.parent.parent.parent, capture_output=True, text=True, check=True).stdout)
    have = set(d["a"]); gone = [a for a in orig["a"] if a not in have]
    try: ok = keep(f"Name a {d['noun']}", [a.split("#")[0].split("|")[0] for a in gone])
    except Exception as e: print("  skip", f.stem, e, flush=True); return
    d["a"] += [gone[k] for k in sorted(ok)]; d["second"] = True
    print(f"  {f.stem:14s} +{len(ok)} back of {len(gone)}", flush=True)
    f.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")))

if __name__ == "__main__":
    fn = {"titanic": titanic, "abcs": abcs, "rescue": rescue, "abcs_rescue": abcs_rescue}[sys.argv[1]]
    with ThreadPoolExecutor(int(os.environ.get("WORKERS", 4))) as ex: list(ex.map(fn, sys.argv[2:]))
