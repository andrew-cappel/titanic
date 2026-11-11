#!/usr/bin/env python3
"""Builds prompts/YYYY-MM-DD.json from Wikidata (CC0).

Usage: python3 scripts/generate.py [YYYY-MM-DD ...]   (default: today and tomorrow, UTC)
Each file holds 4 modes x 5 prompts: [question, "answer/alias|answer|..."].
prompts/used.json remembers which prompts ran so they don't repeat.
"""
import json, random, re, sys, time, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "prompts"
API = "https://query.wikidata.org/sparql"
UA = "TitanicDailyPrompts/1.0 (daily trivia game prompt generator)"

# body uses ?x (answer) and ?s (subject, found by exact English label, most-linked match wins)
T = {
 "films_dir": ("Name five films directed by {}", "?x wdt:P57 ?s; wdt:P31/wdt:P279* wd:Q11424.", 5,
   "Christopher Nolan|Steven Spielberg|Martin Scorsese|Quentin Tarantino|Stanley Kubrick|Alfred Hitchcock|Ridley Scott|Tim Burton|James Cameron|Wes Anderson|David Fincher|Peter Jackson|Hayao Miyazaki|Spike Lee|Denis Villeneuve|Clint Eastwood|Francis Ford Coppola|Woody Allen|Guillermo del Toro|Sofia Coppola|Greta Gerwig|Ron Howard|Robert Zemeckis|Michael Bay|John Carpenter"),
 "films_star": ("Name five films starring {}", "?x wdt:P161 ?s; wdt:P31/wdt:P279* wd:Q11424.", 15,
   "Tom Hanks|Meryl Streep|Leonardo DiCaprio|Denzel Washington|Scarlett Johansson|Brad Pitt|Julia Roberts|Keanu Reeves|Tom Cruise|Nicolas Cage|Will Smith|Sandra Bullock|Harrison Ford|Morgan Freeman|Robin Williams|Jim Carrey|Johnny Depp|Cate Blanchett|Samuel L. Jackson|Natalie Portman|Adam Sandler|Dwayne Johnson|Emma Stone|Matt Damon|Anthony Hopkins"),
 "albums": ("Name five albums by {}", "?x wdt:P175 ?s; wdt:P31/wdt:P279* wd:Q482994.", 3,
   "Taylor Swift|The Beatles|Beyoncé|Radiohead|David Bowie|Madonna|Pink Floyd|Kanye West|Drake|Led Zeppelin|Bob Dylan|Prince|Metallica|Coldplay|Eminem|Kendrick Lamar|Fleetwood Mac|The Rolling Stones|Elton John|Bruce Springsteen|Daft Punk|Green Day|Arctic Monkeys"),
 "songs": ("Name five songs by {}", "?x wdt:P175 ?s; wdt:P31/wdt:P279* wd:Q7366.", 4,
   "Michael Jackson|ABBA|Elvis Presley|Taylor Swift|Rihanna|Lady Gaga|Bruce Springsteen|Elton John|Dolly Parton|Bon Jovi|Nirvana|The Beatles|Queen|Whitney Houston|Britney Spears|Ed Sheeran|Bob Marley|Johnny Cash|The Beach Boys|Stevie Wonder"),
 "books": ("Name five books by {}", "?x wdt:P50 ?s; wdt:P31/wdt:P279* wd:Q7725634.", 5,
   "Stephen King|Agatha Christie|Charles Dickens|Jane Austen|J. R. R. Tolkien|Roald Dahl|Dr. Seuss|Ernest Hemingway|Mark Twain|Leo Tolstoy|Terry Pratchett|Isaac Asimov|Neil Gaiman|Toni Morrison|Kurt Vonnegut|Jules Verne|H. G. Wells|Fyodor Dostoevsky|Virginia Woolf|John Steinbeck|Michael Crichton|Haruki Murakami|Arthur Conan Doyle"),
 "borders": ("Name five countries that border {}", "?x wdt:P47 ?s; wdt:P31 wd:Q6256.", 10,
   "Brazil|China|Russia|Germany|France|Austria|Tanzania|Democratic Republic of the Congo|Turkey|Serbia|Hungary|Zambia|Sudan|Niger|Mali|Iran|Afghanistan|India|Poland|Peru|Saudi Arabia|Ukraine|Switzerland|Colombia|Kazakhstan"),
 "games": ("Name five video games developed by {}", "?x wdt:P178 ?s; wdt:P31 wd:Q7889.", 8,
   "Nintendo|Valve|Blizzard Entertainment|Naughty Dog|FromSoftware|BioWare|Bethesda Game Studios|Insomniac Games|Bungie|Capcom|Square Enix|Ubisoft Montreal|Rockstar North|Sonic Team|Game Freak|Konami|Epic Games|id Software|Retro Studios|Rare"),
 "award": ("Name five winners of the {}", "?x wdt:P166 ?s.", 20,
   "Nobel Prize in Literature|Nobel Peace Prize|Nobel Prize in Physics|Academy Award for Best Actor|Academy Award for Best Actress|Academy Award for Best Director|Ballon d'Or|Grammy Award for Best New Artist|Pulitzer Prize for Fiction|Turing Award|Fields Medal|Academy Award for Best Picture|Palme d'Or|Hugo Award for Best Novel|Presidential Medal of Freedom|Nobel Prize in Chemistry|Academy Award for Best Supporting Actress|Academy Award for Best Animated Feature"),
 "members": ("Name five members (past or present) of {}", "?x wdt:P463 ?s; wdt:P31 wd:Q5.", 3,
   "The Rolling Stones|Fleetwood Mac|Pink Floyd|Guns N' Roses|Red Hot Chili Peppers|Metallica|Journey|Deep Purple|Genesis|The Beach Boys|Wu-Tang Clan|BTS|Spice Girls|Slipknot|Fugees|The Eagles|Black Sabbath|Iron Maiden|Destiny's Child|Backstreet Boys|NSYNC|Monty Python|The Avengers"),
 "divisions": ("Name five states, provinces or regions of {}", "?s wdt:P150 ?x.", 5,
   "Canada|Australia|India|Mexico|Brazil|Germany|Japan|Nigeria|Italy|Spain|France|Argentina|South Africa|China|Austria|Switzerland|Netherlands|Ireland"),
 "teams": ("Name five teams that have played in the {}", "?x wdt:P118 ?s.", 10,
   "National Football League|National Basketball Association|Major League Baseball|National Hockey League|Premier League|La Liga|Serie A|Bundesliga|Major League Soccer|Indian Premier League|Ligue 1|Women's National Basketball Association"),
 "characters": ("Name five characters from {}", "?x wdt:P1441 ?s.", 3,
   "The Simpsons|Friends|Game of Thrones|Breaking Bad|The Office|The Lord of the Rings|Stranger Things|Seinfeld|Family Guy|Pride and Prejudice|Les Misérables|Hamlet|SpongeBob SquarePants|Twin Peaks|The Sopranos|Doctor Who|Star Trek: The Next Generation|One Piece|Naruto|Mad Men|Lost|Buffy the Vampire Slayer|South Park"),
 "endemic": ("Name five species found only in {}", "?x wdt:P183 ?s; wdt:P225 ?tn. FILTER(LCASE(?label) != LCASE(?tn))", 8,
   "Madagascar|Australia|New Zealand|Hawaii|Galápagos Islands|Japan|Cuba|Sri Lanka|Borneo|Tasmania|South Africa|New Guinea"),
 "cities": ("Name five cities in {}", "?x wdt:P31 wd:Q515; wdt:P17 ?s.", 40,
   "Italy|Japan|Germany|Brazil|Spain|France|China|India|Mexico|Canada|Australia|Turkey|Egypt|Poland|Russia|United Kingdom|Argentina|Indonesia|Iran|Pakistan"),
 "tv_network": ("Name five TV series that aired on {}", "?x wdt:P449 ?s; wdt:P31 wd:Q5398426.", 20,
   "HBO|NBC|CBS|American Broadcasting Company|Netflix|BBC One|Fox Broadcasting Company|AMC|Disney Channel|Cartoon Network|Nickelodeon|MTV|Comedy Central|FX|Showtime|The CW|Adult Swim|Prime Video|Hulu|Channel 4"),
 "studio": ("Name five films produced by {}", "?x wdt:P272 ?s; wdt:P31/wdt:P279* wd:Q11424.", 10,
   "Pixar|Walt Disney Animation Studios|DreamWorks Animation|Studio Ghibli|Marvel Studios|Lucasfilm|Blumhouse Productions|A24|Illumination|Aardman Animations|Legendary Entertainment|Amblin Entertainment|Working Title Films|Pixar Animation Studios"),
 "players": ("Name five players who have played for {}", "?x wdt:P54 ?s; wdt:P31 wd:Q5.", 25,
   "Manchester United F.C.|Real Madrid CF|FC Barcelona|Los Angeles Lakers|Chicago Bulls|New York Yankees|Boston Celtics|Dallas Cowboys|New England Patriots|Liverpool F.C.|Juventus FC|Golden State Warriors|Arsenal F.C.|AC Milan|FC Bayern Munich|Paris Saint-Germain F.C.|Brazil national football team|Argentina national football team"),
}
MIN_ANSWERS, PER_TEMPLATE, PER_DAY = 8, 2, 20

def run(q):
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode({"query": q, "format": "json"}), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["results"]["bindings"]

def sparql(body, subj, minsl):
    u = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode({"action": "wbsearchentities", "search": subj, "language": "en", "limit": 1, "format": "json"})
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=30) as r:
        hit = json.load(r).get("search")
    if not hit: return []
    qid = hit[0]["id"]
    return run(f"""SELECT ?x ?label ?sl ?human (GROUP_CONCAT(DISTINCT ?alt; separator="\\t") AS ?alts) WHERE {{
  VALUES ?s {{ wd:{qid} }}
  {body}
  ?x wikibase:sitelinks ?sl. FILTER(?sl >= {minsl})
  ?x rdfs:label ?label. FILTER(LANG(?label)="en")
  OPTIONAL {{ ?x skos:altLabel ?alt. FILTER(LANG(?alt)="en") }}
  BIND(EXISTS {{ ?x wdt:P31 wd:Q5 }} AS ?human)
}} GROUP BY ?x ?label ?sl ?human ORDER BY DESC(?sl) LIMIT 150""")

clean = lambda s: re.sub(r"\s+", " ", re.sub(r"[|/\t]", " ", re.sub(r"\s*\(.*?\)\s*", " ", s))).strip()

def build(rows):
    seen, out = set(), []
    for r in rows:
        label = clean(r["label"]["value"])
        if not label or label.lower() in seen or re.match(r"^Q\d+$", label): continue
        seen.add(label.lower())
        keys = [label] + [clean(a) for a in r.get("alts", {}).get("value", "").split("\t") if a and len(a) <= 40][:6]
        if r["human"]["value"] == "true" and " " in label: keys.append(label.split(" ")[-1])
        out.append([k for i, k in enumerate(keys) if k and k.lower() not in {x.lower() for x in keys[:i]}])
    # drop surname aliases that collide between answers
    last = {}
    for a in out:
        for k in a[1:]: last[k.lower()] = last.get(k.lower(), 0) + 1
    return [[a[0]] + [k for k in a[1:] if last[k.lower()] == 1] for a in out]

def make(day, used):
    rng = random.Random("titanic" + day)
    pool = [(t, s) for t, v in T.items() for s in v[3].split("|") if f"{t}:{s}" not in used]
    rng.shuffle(pool)
    got, count = [], {}
    for t, s in pool:
        if len(got) == PER_DAY: break
        if count.get(t, 0) >= PER_TEMPLATE: continue
        text, body, minsl, _ = T[t]
        try: rows = sparql(body, s, minsl)
        except Exception as e: print("  skip", t, s, e); time.sleep(3); continue
        ans = build(rows); time.sleep(1)
        print(f"  {len(ans):3d}  {text.format(s)}", flush=True)
        if len(ans) < MIN_ANSWERS: continue
        got.append((len(ans), [text.format(s), "|".join("/".join(a) for a in ans)], f"{t}:{s}"))
        count[t] = count.get(t, 0) + 1
    if len(got) < PER_DAY: raise SystemExit(f"only {len(got)} prompts for {day}")
    got.sort(key=lambda g: -g[0])  # most answers = easiest
    used.extend(g[2] for g in got)
    return {"date": day, "source": "Wikidata (CC0)", "modes": [[g[1] for g in got[i*5:i*5+5]] for i in range(4)]}

def main():
    OUT.mkdir(exist_ok=True)
    uf = OUT / "used.json"
    used = json.loads(uf.read_text()) if uf.exists() else []
    now = datetime.now(timezone.utc).date()
    days = sys.argv[1:] or [str(now), str(now + timedelta(days=1))]
    for day in days:
        f = OUT / f"{day}.json"
        if f.exists(): print("exists", f.name); continue
        print("building", day)
        f.write_text(json.dumps(make(day, used), ensure_ascii=False, separators=(",", ":")))
        uf.write_text(json.dumps(used))
    # once every pairing is used, start over
    if len(used) > sum(len(v[3].split("|")) for v in T.values()) - PER_DAY * 2: uf.write_text("[]")

if __name__ == "__main__":
    main()
