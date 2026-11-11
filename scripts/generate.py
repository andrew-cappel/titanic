#!/usr/bin/env python3
"""Builds prompts/YYYY-MM-DD.json from Wikidata (CC0).

Usage: python3 scripts/generate.py [YYYY-MM-DD ...]   (default: today and tomorrow, UTC)
Each file holds 4 modes x 5 prompts: [question, "answer/alias|answer|..."].
prompts/used.json remembers which prompts ran so they don't repeat.
"""
import json, random, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "prompts"
API = "https://query.wikidata.org/sparql"
UA = "TitanicDailyPrompts/1.0 (daily trivia game prompt generator)"

# key: (category, prompt, body, min sitelinks, subjects). Body uses ?x (answer) and ?s (subject).
# Subjects are "Wikidata search text" or "search text=how it reads in the prompt".
# Each difficulty gets 5 different categories; no category more than 3 times a day.
C = "?x wdt:P17 ?s; wdt:P31/wdt:P279* wd:{}."   # things of a type in a country
T = {
 "films_dir": ("film", "Name five films directed by {}", "?x wdt:P57 ?s; wdt:P31/wdt:P279* wd:Q11424.", 5,
   "Christopher Nolan|Steven Spielberg|Martin Scorsese|Quentin Tarantino|Stanley Kubrick|Alfred Hitchcock|Ridley Scott|Tim Burton|James Cameron|Wes Anderson|David Fincher|Peter Jackson|Hayao Miyazaki|Spike Lee|Denis Villeneuve|Clint Eastwood|Francis Ford Coppola|Woody Allen|Guillermo del Toro|Ron Howard|Robert Zemeckis|Michael Bay|John Carpenter"),
 "films_star": ("film", "Name five films starring {}", "?x wdt:P161 ?s; wdt:P31/wdt:P279* wd:Q11424.", 15,
   "Tom Hanks|Meryl Streep|Leonardo DiCaprio|Denzel Washington|Scarlett Johansson|Brad Pitt|Julia Roberts|Keanu Reeves|Tom Cruise|Nicolas Cage|Will Smith|Sandra Bullock|Harrison Ford|Morgan Freeman|Robin Williams|Jim Carrey|Johnny Depp|Cate Blanchett|Samuel L. Jackson|Natalie Portman|Adam Sandler|Dwayne Johnson|Matt Damon|Anthony Hopkins"),
 "studio": ("film", "Name five films produced by {}", "?x wdt:P272 ?s; wdt:P31/wdt:P279* wd:Q11424.", 10,
   "Pixar Animation Studios=Pixar|Walt Disney Animation Studios|DreamWorks Animation|Studio Ghibli|Marvel Studios|Lucasfilm|Blumhouse Productions|A24|Illumination|Aardman Animations|Legendary Entertainment|Amblin Entertainment"),
 "tv_network": ("tv", "Name five TV series that aired on {}", "?x wdt:P449 ?s; wdt:P31/wdt:P279* wd:Q5398426.", 20,
   "HBO|NBC|CBS|American Broadcasting Company=ABC|Netflix|BBC One|Fox Broadcasting Company=Fox|AMC|Disney Channel|Cartoon Network|Nickelodeon|MTV|Comedy Central|FX|Showtime|The CW|Adult Swim|Prime Video|Hulu|Channel 4"),
 "characters": ("tv", "Name five characters from {}", "{ ?x wdt:P1441 ?s } UNION { ?x wdt:P1080 ?s } UNION { ?x wdt:P8345 ?s }", 3,
   "The Simpsons|Friends|Game of Thrones|Breaking Bad|The Office|The Lord of the Rings|Stranger Things|Seinfeld|Family Guy|SpongeBob SquarePants|Twin Peaks|The Sopranos|Doctor Who|Star Trek: The Next Generation|One Piece|Naruto|Mad Men|Lost|Buffy the Vampire Slayer|South Park|Pride and Prejudice|Hamlet"),
 "albums": ("music", "Name five albums by {}", "?x wdt:P175 ?s; wdt:P31/wdt:P279* wd:Q482994.", 3,
   "Taylor Swift|The Beatles|Beyoncé|Radiohead|David Bowie|Madonna|Pink Floyd|Kanye West|Drake|Led Zeppelin|Bob Dylan|Prince|Metallica|Coldplay|Eminem|Kendrick Lamar|Fleetwood Mac|The Rolling Stones|Elton John|Bruce Springsteen|Daft Punk|Green Day|Arctic Monkeys"),
 "songs": ("music", "Name five songs by {}", "?x wdt:P175 ?s; wdt:P31/wdt:P279* wd:Q7366.", 4,
   "Michael Jackson|ABBA|Elvis Presley|Taylor Swift|Rihanna|Lady Gaga|Bruce Springsteen|Elton John|Dolly Parton|Bon Jovi|Nirvana|The Beatles|Queen band=Queen|Whitney Houston|Britney Spears|Ed Sheeran|Bob Marley|Johnny Cash|The Beach Boys|Stevie Wonder"),
 "members": ("music", "Name five members (past or present) of {}", "{ ?x wdt:P463 ?s } UNION { ?s wdt:P527 ?x } ?x wdt:P31 wd:Q5.", 3,
   "The Rolling Stones|Fleetwood Mac|Pink Floyd|Guns N' Roses|Red Hot Chili Peppers|Metallica|Journey|Deep Purple|Genesis|The Beach Boys|Wu-Tang Clan|BTS|Spice Girls|Slipknot|The Eagles|Black Sabbath|Iron Maiden|Destiny's Child|Backstreet Boys|NSYNC|Monty Python"),
 "books": ("books", "Name five books by {}", "?x wdt:P50 ?s; wdt:P31/wdt:P279* wd:Q7725634.", 5,
   "Stephen King|Agatha Christie|Charles Dickens|Jane Austen|J. R. R. Tolkien|Roald Dahl|Dr. Seuss|Ernest Hemingway|Mark Twain|Leo Tolstoy|Terry Pratchett|Isaac Asimov|Neil Gaiman|Toni Morrison|Kurt Vonnegut|Jules Verne|H. G. Wells|Fyodor Dostoevsky|Virginia Woolf|John Steinbeck|Michael Crichton|Haruki Murakami|Arthur Conan Doyle"),
 "games": ("games", "Name five video games developed by {}", "?x wdt:P178 ?s; wdt:P31/wdt:P279* wd:Q7889.", 8,
   "Nintendo|Valve|Blizzard Entertainment|Naughty Dog|FromSoftware|BioWare|Bethesda Game Studios|Insomniac Games|Bungie|Capcom|Square Enix|Ubisoft Montreal|Rockstar North|Sonic Team|Game Freak|Konami|Epic Games|id Software|Rare"),
 "teams": ("sport", "Name five teams that have played in the {}", "{ ?x wdt:P118 ?s } UNION { ?s wdt:P1923 ?x }", 10,
   "National Football League=NFL|National Basketball Association=NBA|Major League Baseball|National Hockey League=NHL|Premier League|La Liga|Serie A|Bundesliga|Major League Soccer|Indian Premier League|Ligue 1"),
 "players": ("sport", "Name five players who have played for {}", "?x wdt:P54 ?s; wdt:P31 wd:Q5.", 25,
   "Manchester United F.C.=Manchester United|Real Madrid CF=Real Madrid|FC Barcelona|Los Angeles Lakers|Chicago Bulls|New York Yankees|Boston Celtics|Dallas Cowboys|New England Patriots|Liverpool F.C.=Liverpool|Juventus FC=Juventus|Golden State Warriors|Arsenal F.C.=Arsenal|AC Milan|FC Bayern Munich=Bayern Munich|Brazil national football team=Brazil's national football team"),
 "borders": ("countries", "Name five countries that border {}", "?x wdt:P47 ?s. { ?x wdt:P31 wd:Q6256 } UNION { ?x wdt:P31 wd:Q3624078 }", 10,
   "Brazil|China|Russia|Germany|France|Austria|Tanzania|Democratic Republic of the Congo=the Democratic Republic of the Congo|Turkey|Serbia|Hungary|Zambia|Sudan|Niger|Mali|Iran|Afghanistan|India|Poland|Peru|Saudi Arabia|Ukraine|Switzerland|Colombia|Kazakhstan"),
 "continent": ("countries", "Name five countries in {}", "?x wdt:P30 ?s. { ?x wdt:P31 wd:Q6256 } UNION { ?x wdt:P31 wd:Q3624078 }", 10,
   "Africa|Europe|Asia|South America|North America|Oceania"),
 "divisions": ("countries", "Name five states, provinces or regions of {}", "?s wdt:P150 ?x.", 5,
   "Canada|Australia|India|Mexico|Brazil|Germany|Japan|Nigeria|Italy|Spain|France|Argentina|South Africa|China|Austria|Switzerland|Netherlands=the Netherlands|Ireland"),
 "cities": ("cities", "Name five cities in {}", "?x wdt:P17 ?s. { ?x wdt:P31/wdt:P279* wd:Q515 } UNION { ?x wdt:P31/wdt:P279* wd:Q486972 } UNION { ?x wdt:P31/wdt:P279* wd:Q15284 }", 40,
   "Italy|Japan|Germany|Brazil|Spain|France|China|India|Mexico|Canada|Australia|Turkey|Egypt|Poland|Russia|United Kingdom=the United Kingdom|Argentina|Indonesia|Iran|Pakistan|United States=the United States"),
 "heritage": ("landmarks", "Name five UNESCO World Heritage Sites in {}", "?x wdt:P17 ?s; wdt:P1435 wd:Q9259.", 10,
   "Italy|China|Spain|France|Germany|India|Mexico|United Kingdom=the United Kingdom|Peru|Egypt|Japan|Greece|Turkey|Iran|Brazil|Australia|United States=the United States"),
 "buildings": ("landmarks", "Name five buildings designed by {}", "?x wdt:P84 ?s.", 5,
   "Frank Lloyd Wright|Zaha Hadid|Antoni Gaudí|Le Corbusier|Frank Gehry|I. M. Pei|Norman Foster|Renzo Piano|Christopher Wren|Ludwig Mies van der Rohe|Oscar Niemeyer|Santiago Calatrava"),
 "ranges": ("mountains", "Name five mountain ranges in {}", "{ ?x wdt:P30 ?s } UNION { ?x wdt:P17 ?s } ?x wdt:P31/wdt:P279* wd:Q46831.", 8,
   "Europe|Asia|North America|South America|Africa|United States=the United States|China|Russia|Canada|Italy|Spain|France"),
 "mountains": ("mountains", "Name five mountains in {}", "?x wdt:P17 ?s. { ?x wdt:P31/wdt:P279* wd:Q8502 } UNION { ?x wdt:P31/wdt:P279* wd:Q207326 } UNION { ?x wdt:P31/wdt:P279* wd:Q1595289 }", 10,
   "Switzerland|Nepal|Japan|United States=the United States|Italy|Austria|Canada|Chile|New Zealand|Argentina|France|Pakistan|Tanzania|Greece"),
 "volcanoes": ("mountains", "Name five volcanoes in {}", C.format("Q8072"), 5,
   "Indonesia|Japan|Italy|Iceland|United States=the United States|Chile|Mexico|Ecuador|Philippines=the Philippines|New Zealand|Russia|Guatemala"),
 "rivers": ("water", "Name five rivers in {}", "?x wdt:P17 ?s. { ?x wdt:P31/wdt:P279* wd:Q4022 } UNION { ?x wdt:P31/wdt:P279* wd:Q47521 }", 15,
   "Germany|France|Russia|China|India|Brazil|United States=the United States|Canada|Poland|Italy|Spain|United Kingdom=the United Kingdom|Australia|Ukraine|Austria"),
 "lakes": ("water", "Name five lakes in {}", "?x wdt:P17 ?s. { ?x wdt:P31/wdt:P279* wd:Q23397 } UNION { ?x wdt:P31/wdt:P279* wd:Q131681 }", 10,
   "Canada|Finland|Italy|Switzerland|United States=the United States|Russia|Sweden|Germany|Austria|China|Chile|Argentina|New Zealand"),
 "islands": ("water", "Name five islands of {}", "?x wdt:P17 ?s. { ?x wdt:P31/wdt:P279* wd:Q23442 } UNION { ?x wdt:P31/wdt:P279* wd:Q33837 }", 10,
   "Greece|Indonesia|Philippines=the Philippines|Japan|Italy|Croatia|Norway|Canada|Denmark|Spain|United Kingdom=the United Kingdom|Estonia|Sweden|France"),
 "parks": ("nature", "Name five national parks in {}", C.format("Q46169"), 5,
   "United States=the United States|Canada|Australia|Kenya|South Africa|New Zealand|Costa Rica|Japan|India|Tanzania|Argentina|Chile|Poland|Spain"),
 "species": ("animals", "Name five {}", "?x wdt:P171+ ?s; wdt:P105 wd:Q7432; wdt:P225 ?tn. FILTER(LCASE(?label) != LCASE(?tn))", 15,
   "Felidae=species of wild cat|Canidae=wild species of the dog family|Ursidae=species of bear|Cetacea=species of whale or dolphin|Accipitridae=species of hawk, eagle or kite|Psittaciformes=species of parrot|Testudines=species of turtle or tortoise|Serpentes=species of snake|Primates=species of primate|Selachimorpha=species of shark|Anatidae=species of duck, goose or swan|Strigiformes=species of owl|Pinnipedia=species of seal, sea lion or walrus|Cervidae=species of deer|Bovidae=species of antelope, cattle or goat|Crocodilia=species of crocodile or alligator|Spheniscidae=species of penguin|Mustelidae=species of the weasel family|Equidae=species of horse, zebra or donkey|Lepidoptera=species of butterfly or moth"),
 "endemic": ("animals", "Name five species found only in {}", "?x wdt:P183 ?s; wdt:P225 ?tn. FILTER(LCASE(?label) != LCASE(?tn))", 8,
   "Madagascar|Australia|New Zealand|Hawaii|Galápagos Islands=the Galápagos Islands|Japan|Cuba|Sri Lanka|Borneo|Tasmania|South Africa|New Guinea"),
 "breeds": ("animals", "Name five {}", "?x wdt:P31 ?s.", 5,
   "dog breed=dog breeds|cat breed=cat breeds|horse breed=horse breeds|cattle breed=cattle breeds|chicken breed=chicken breeds|sheep breed=sheep breeds"),
 "dishes": ("food", "Name five dishes from {}", "{ ?x wdt:P495 ?s } UNION { ?x wdt:P17 ?s } UNION { ?x wdt:P2341 ?s } UNION { ?x wdt:P1071/wdt:P17 ?s } UNION { ?x wdt:P495/wdt:P17 ?s } ?x (wdt:P31|wdt:P279)/wdt:P279* wd:Q2095.", 8,
   "Italy|Japan|Mexico|India|France|China|Thailand|Spain|Greece|Turkey|South Korea|Germany|Vietnam|Peru|Lebanon|Morocco"),
 "cheeses": ("food", "Name five cheeses from {}", "{ ?x wdt:P495 ?s } UNION { ?x wdt:P17 ?s } UNION { ?x wdt:P2341 ?s } UNION { ?x wdt:P1071/wdt:P17 ?s } UNION { ?x wdt:P495/wdt:P17 ?s } ?x (wdt:P31|wdt:P279)/wdt:P279* wd:Q10943.", 5,
   "France|Italy|Switzerland|Netherlands=the Netherlands|United Kingdom=the United Kingdom|Spain|Greece"),
 "paintings": ("art", "Name five paintings by {}", "?x wdt:P170 ?s; wdt:P31 wd:Q3305213.", 8,
   "Vincent van Gogh|Leonardo da Vinci|Claude Monet|Rembrandt|Johannes Vermeer|Pablo Picasso|Salvador Dalí|Frida Kahlo|Edvard Munch|Sandro Botticelli|Caravaggio|Gustav Klimt|Raphael|Edward Hopper|J. M. W. Turner"),
 "office": ("history", "Name five people who have served as {}", "?x wdt:P39 ?s.", 5,
   "President of the United States|Prime Minister of the United Kingdom|Prime Minister of Canada|Chancellor of Germany|President of France|Prime Minister of Australia|Secretary-General of the United Nations|Prime Minister of India|Prime Minister of Japan|pope=pope|Prime Minister of Italy|President of Brazil"),
 "battles": ("history", "Name five battles of {}", "{ ?x wdt:P361+ ?s } UNION { ?x wdt:P607 ?s } ?x wdt:P31/wdt:P279* wd:Q645883.", 5,
   "American Civil War=the American Civil War|Napoleonic Wars=the Napoleonic Wars|World War I|Hundred Years' War=the Hundred Years' War|American Revolutionary War=the American Revolutionary War|Wars of the Roses=the Wars of the Roses|Seven Years' War=the Seven Years' War|Pacific War=the Pacific War|Vietnam War=the Vietnam War|Korean War=the Korean War"),
 "award": ("awards", "Name five winners of the {}", "{ ?x wdt:P166 ?s } UNION { ?s wdt:P1346 ?x }", 20,
   "Nobel Prize in Literature|Nobel Peace Prize|Nobel Prize in Physics|Academy Award for Best Actor|Academy Award for Best Actress|Academy Award for Best Director|Ballon d'Or|Grammy Award for Best New Artist|Pulitzer Prize for Fiction|Turing Award|Fields Medal|Academy Award for Best Picture|Palme d'Or|Hugo Award for Best Novel|Nobel Prize in Chemistry"),
 "moons": ("space", "Name five moons of {}", "?x wdt:P397 ?s.", 3,
   "Jupiter|Saturn|Uranus|Neptune"),
 "occupation": ("people", "Name five famous {}", "?x wdt:P106 ?s; wdt:P31 wd:Q5.", 15,
   "conquistador=conquistadors|astronaut=astronauts|pirate=pirates|explorer=explorers|inventor=inventors|philosopher=philosophers|composer=composers|magician=magicians|gladiator=gladiators|samurai=samurai"),
 "letters": ("words", "Name five countries with \"{}\" in their name", "?x wdt:P31 wd:Q6256; rdfs:label ?nm. filter(LANG(?nm)=\"en\" && CONTAINS(LCASE(?nm), \"{lit}\"))", 10,
   "ia|an|land|stan|ar|ra|en|or|ma|ga", True),
 "states": ("words", "Name five U.S. states that start with {}", "?x wdt:P31 wd:Q35657; rdfs:label ?nm. filter(LANG(?nm)=\"en\" && STRSTARTS(?nm, \"{lit}\"))", 5,
   "M|N|I|A|C|W|O", True),
}
# Easy mode draws only from these well-known subjects (plus the letter games); the rest are ranked by fame.
EASY = {
 "films_star": "Tom Hanks|Leonardo DiCaprio|Will Smith|Tom Cruise|Jim Carrey|Adam Sandler|Dwayne Johnson",
 "films_dir": "Steven Spielberg|Tim Burton", "studio": "Pixar Animation Studios=Pixar|Walt Disney Animation Studios|DreamWorks Animation|Marvel Studios",
 "characters": "The Simpsons|Friends|SpongeBob SquarePants|Family Guy|The Office|Stranger Things",
 "tv_network": "Nickelodeon|Disney Channel|Cartoon Network", "songs": "Michael Jackson|Taylor Swift|The Beatles|Queen band=Queen|Elvis Presley|ABBA",
 "members": "Spice Girls|Backstreet Boys|NSYNC", "books": "Dr. Seuss|Roald Dahl|Stephen King", "games": "Nintendo",
 "teams": "National Football League=NFL|National Basketball Association=NBA|Major League Baseball|Premier League|National Hockey League=NHL",
 "players": "Manchester United F.C.=Manchester United|Real Madrid CF=Real Madrid|FC Barcelona|Los Angeles Lakers|FC Bayern Munich=Bayern Munich|Chicago Bulls|New York Yankees",
 "borders": "China|Russia|Germany|France|Brazil", "continent": "Africa|Europe|Asia|South America",
 "cities": "Italy|Germany|Spain|France|Japan|United States=the United States|Russia|United Kingdom=the United Kingdom|Canada|Australia|Mexico|India|China|Brazil",
 "divisions": "Canada|Australia", "species": "Felidae=species of wild cat|Ursidae=species of bear|Selachimorpha=species of shark|Cetacea=species of whale or dolphin",
 "breeds": "dog breed=dog breeds|cat breed=cat breeds|horse breed=horse breeds", "dishes": "Italy|Mexico|Japan|France",
 "office": "President of the United States", "paintings": "Vincent van Gogh", "occupation": "conquistador=conquistadors|astronaut=astronauts|pirate=pirates|explorer=explorers",
 "letters": "ia|an|land|stan|ar|ra|en|or|ma|ga", "states": "M|N|I|A|C|W|O",
 "ranges": "Europe|Asia|North America|South America|United States=the United States",
}
# Fixed difficulty per prompt type (2 Medium, 3 Hard, 4 Impossible), with per-subject overrides.
TIER = {"members": 3, "heritage": 3, "paintings": 3, "battles": 3, "rivers": 3, "lakes": 3, "islands": 3, "parks": 3, "award": 3,
        "mountains": 4, "volcanoes": 4, "moons": 4, "endemic": 4, "cheeses": 4, "buildings": 4}
SUBJ_TIER = {"award:" + a: 4 for a in ["Fields Medal", "Turing Award", "Hugo Award for Best Novel", "Nobel Prize in Chemistry", "Nobel Prize in Physics", "Pulitzer Prize for Fiction", "Palme d'Or"]}
SUBJ_TIER.update({"award:" + a: 2 for a in ["Academy Award for Best Actor", "Academy Award for Best Actress", "Academy Award for Best Picture", "Ballon d'Or"]})
SUBJ_TIER.update({"species:" + a: 3 for a in ["Mustelidae=species of the weasel family", "Lepidoptera=species of butterfly or moth", "Accipitridae=species of hawk, eagle or kite", "Strigiformes=species of owl", "Pinnipedia=species of seal, sea lion or walrus", "Bovidae=species of antelope, cattle or goat", "Psittaciformes=species of parrot", "Anatidae=species of duck, goose or swan"]})
SUBJ_TIER.update({"breeds:" + a: 3 for a in ["cattle breed=cattle breeds", "chicken breed=chicken breeds", "sheep breed=sheep breeds"]})
tier = lambda t, s: SUBJ_TIER.get(f"{t}:{s}", TIER.get(t, 2))
# What a typed answer must satisfy to be accepted (default: the template's own body).
# People/works only need the relationship, whatever Wikidata calls the thing itself.
CHECK = {
 "films_dir": "?x wdt:P57 ?s.", "films_star": "?x wdt:P161 ?s.", "studio": "{ ?x wdt:P272 ?s } UNION { ?x wdt:P750 ?s }",
 "tv_network": "?x wdt:P449 ?s.", "albums": "?x wdt:P175 ?s.", "songs": "{ ?x wdt:P175 ?s } UNION { ?x wdt:P86 ?s } UNION { ?x wdt:P676 ?s }",
 "books": "?x wdt:P50 ?s.", "games": "{ ?x wdt:P178 ?s } UNION { ?x wdt:P123 ?s }", "paintings": "?x wdt:P170 ?s.",
 "players": "?x wdt:P54 ?s.", "members": "{ ?x wdt:P463 ?s } UNION { ?s wdt:P527 ?x }", "battles": "{ ?x wdt:P361+ ?s } UNION { ?x wdt:P607 ?s }",
 "volcanoes": "?x wdt:P17 ?s. { ?x wdt:P31/wdt:P279* wd:Q8072 } UNION { ?x wdt:P31/wdt:P279* wd:Q8502 }",
 "endemic": "?x wdt:P183 ?s.", "species": "?x wdt:P171+ ?s.",
}
MIN_ANSWERS, PER_CATEGORY, PER_DAY = 8, 2, 20

QUERY = """SELECT ?x ?label ?sl ?human (GROUP_CONCAT(DISTINCT ?alt; separator="\\t") AS ?alts) WHERE {{
  {values}
  {body}
  ?x wikibase:sitelinks ?sl. FILTER(?sl >= {minsl})
  ?x rdfs:label ?label. FILTER(LANG(?label)="en")
  OPTIONAL {{ ?x skos:altLabel ?alt. FILTER(LANG(?alt)="en") }}
  BIND(EXISTS {{ ?x wdt:P31 wd:Q5 }} AS ?human)
}} GROUP BY ?x ?label ?sl ?human ORDER BY DESC(?sl) LIMIT 400"""

def run(q):
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode({"query": q, "format": "json"}), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["results"]["bindings"]

def sparql(body, subj, minsl, lit=False):
    if lit:
        return "", run(QUERY.format(values="", body=body.replace("{lit}", subj.lower() if "LCASE" in body else subj), minsl=minsl))
    u = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode({"action": "wbsearchentities", "search": subj, "language": "en", "limit": 1, "format": "json"})
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=30) as r:
        hit = json.load(r).get("search")
    if not hit: return None, []
    qid = hit[0]["id"]
    return qid, run(QUERY.format(values=f"VALUES ?s {{ wd:{qid} }}", body=body, minsl=minsl))

clean = lambda s: re.sub(r"\s+", " ", re.sub(r"[|/\t]", " ", re.sub(r"\s*\(.*?\)\s*", " ", s))).strip()

def build(rows):
    seen, out, ids = set(), [], []
    for r in rows:
        label = clean(r["label"]["value"])
        if not label or label.lower() in seen or re.match(r"^Q\d+$", label): continue
        seen.add(label.lower())
        keys = [label] + [clean(a) for a in r.get("alts", {}).get("value", "").split("\t") if a and len(a) <= 40][:6]
        if r["human"]["value"] == "true" and " " in label: keys.append(label.split(" ")[-1])
        out.append([k for i, k in enumerate(keys) if k and k.lower() not in {x.lower() for x in keys[:i]}])
        ids.append(r["x"]["value"].rsplit("/", 1)[1])
    # drop surname aliases that collide between answers
    last = {}
    for a in out:
        for k in a[1:]: last[k.lower()] = last.get(k.lower(), 0) + 1
    return [[a[0]] + [k for k in a[1:] if last[k.lower()] == 1] for a in out], ids

def fwd(body):
    """Make Wikidata walk class/part-of chains upward from the answer (21s -> 0.3s for live checks)."""
    return re.sub(r'(wdt:P\d+[*+]\s+(?:wd:Q\d+|\?s))\s*([.}])', r'\1 . hint:Prior hint:gearing "forward" \2', body)

def fetch(t, s):
    """One prompt: (answer count, category, fame, [question, answers, subject id, check body, answer ids], key) or None."""
    v = T[t]; cat, text, body, minsl, lit = v[0], v[1], v[2], v[3], len(v) > 5
    search, disp = (s.split("=") + [s])[:2]
    for attempt in range(5):  # Wikidata rate-limits bursts (HTTP 429): wait and retry instead of skipping
        try: qid, rows = sparql(body, search, minsl, lit); break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 4: print("  skip", t, s, e, flush=True); return None
            wait = int(e.headers.get("Retry-After") or 0) or 20 * (attempt + 1)
            print(f"  rate limited, waiting {wait}s", flush=True); time.sleep(wait)
        except Exception as e: print("  skip", t, s, e, flush=True); time.sleep(3); return None
    ans, ids = build(rows); time.sleep(2)
    print(f"  {len(ans):3d}  {text.format(disp)}", flush=True)
    if len(ans) < MIN_ANSWERS: return None
    fame = sorted(int(r["sl"]["value"]) for r in rows[:10])[len(rows[:10]) // 2]  # median fame of top answers
    chk = fwd(CHECK.get(t, body)).replace("{lit}", search.lower() if "LCASE" in body else search).split(" FILTER")[0]
    return (len(ans), cat, fame, [text.format(disp), "|".join("/".join(a) for a in ans), qid, chk, ",".join(ids)], f"{t}:{s}")

def pick(pool, n, cats, cc, tused):
    """Round-robin over topics so no topic repeats within the n picked."""
    got, mine = [], set()
    while len(got) < n and any(pool[c] for c in cats if c not in mine and cc.get(c, 0) < PER_CATEGORY):
        for c in cats:
            if len(got) >= n or c in mine or cc.get(c, 0) >= PER_CATEGORY: continue
            while pool[c]:
                t, s = pool[c].pop()
                if t in tused: continue
                g = fetch(t, s)
                if g: got.append(g); cc[c] = cc.get(c, 0) + 1; tused.add(t); mine.add(c); break
        if len(mine) == len(cats): mine = set()  # allow a second round of topics if needed
    return got

def make(day, used):
    rng = random.Random("titanic" + day)
    easy = {f"{t}:{s}" for t, v in EASY.items() for s in v.split("|")}
    allp = [(t, s) for t, v in T.items() for s in v[4].split("|") if f"{t}:{s}" not in used]
    rng.shuffle(allp)
    cats = sorted({v[0] for v in T.values()}); rng.shuffle(cats)
    lvl = lambda p: 1 if f"{p[0]}:{p[1]}" in easy else tier(*p)
    cc, tused, modes = {}, set(), []
    for L in (1, 2, 3, 4):   # each difficulty draws only from its own level, 5 different topics
        pool = {c: [p for p in allp if T[p[0]][0] == c and lvl(p) == L] for c in cats}
        m = pick(pool, 5, cats, cc, tused)
        if len(m) < 5:  # small levels may reuse a topic from another difficulty (never within this one)
            m += pick(pool, 5 - len(m), [c for c in cats if c not in {x[1] for x in m}], {}, tused)
        if len(m) < 5 and L > 1:  # last resort: borrow from the level below
            low = {c: [p for p in allp if T[p[0]][0] == c and lvl(p) == L - 1 and p[0] not in tused] for c in cats}
            m += pick(low, 5 - len(m), [c for c in cats if c not in {x[1] for x in m}], {}, tused)
        if len(m) < 5: raise SystemExit(f"not enough level-{L} prompts for {day}")
        modes.append(m)
    used.extend(g[4] for m in modes for g in m)
    for m in modes: rng.shuffle(m)
    return {"date": day, "source": "Wikidata (CC0)", "modes": [[g[3] for g in m] for m in modes]}

def safe_make(day, used):
    try: return make(day, used)
    except SystemExit:  # a level ran out of unused prompts: start the rotation over
        used.clear(); return make(day, used)

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
        f.write_text(json.dumps(safe_make(day, used), ensure_ascii=False, separators=(",", ":")))
        uf.write_text(json.dumps(used))
    # once every pairing is used, start over
    if len(used) > sum(len(v[4].split("|")) for v in T.values()) - PER_DAY * 2: uf.write_text("[]")

if __name__ == "__main__":
    main()
