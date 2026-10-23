"""Builds us-places.tsv.gz: every US city, town, village, borough, CDP and (where they are the local government, as in New Jersey and
Pennsylvania) township, with its internal point, from the US Census Bureau Gazetteer files (public domain). The server reads it to place
each job ("Cherry Hill, NJ" -> 39.92,-75.01), so "near you" and the distance filter work for jobs the app's short city list misses.

  python tools/make-us-places.py 2024_Gaz_place_national.txt 2024_Gaz_cousubs_national.txt
  (from https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/ : 2024_Gaz_place_national.zip, 2024_Gaz_cousubs_national.zip)

One line per place, sorted: "<state>|<name>\\t<lat>\\t<lng>", the name as jobs_api.place_key() makes it (lower case, no punctuation,
Saint/Fort/Mount as st/ft/mt, the Census suffix such as "city", "CDP" or "township" taken off). Where two places in a state share a
name, a place (city, borough, town, village) wins over a CDP, a CDP over a township, then the larger one."""
import gzip
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ.setdefault("UAPLY_CONFIG_FILE", "none")
import jobs_api as J  # noqa: E402

BALANCE = re.compile(r"\s+(?:\(balance\)|consolidated government|metropolitan government|unified government|urban county)$")
# the Census' own kind of place, in lower case after the name ("Jersey City city": only the last word goes)
SUFFIX = re.compile(r"\s+(?:city and borough|charter township|city|town|village|borough|CDP|township|municipality|plantation|comunidad|zona urbana)$")


def rows(path, kind):
    with open(path, encoding="utf-8") as f:
        head = f.readline().rstrip("\n").split("\t")
        col = {h.strip(): i for i, h in enumerate(head)}
        for line in f:
            p = line.rstrip("\n").split("\t")
            st, name = p[col["USPS"]].strip(), p[col["NAME"]].strip()
            if kind == "cousub" and not re.search(r" (?:township|town|borough|village|city|plantation)$", name):
                continue                          # census county divisions, precincts, barrios: not names people give a place
            base = name
            while BALANCE.search(base):           # "Nashville-Davidson metropolitan government (balance)" -> "Nashville-Davidson"
                base = BALANCE.sub("", base).strip()
            base = SUFFIX.sub("", base).strip()
            rank = (0 if kind == "place" and not name.endswith(" CDP") else 1 if kind == "place" else 2, -float(p[col["ALAND"]] or 0))
            lat, lng = float(p[col["INTPTLAT"]]), float(p[col["INTPTLONG"]].strip())
            names = [base]
            if re.search(r"government|\(balance\)", name) and re.search(r"[-/]", base):
                names.append(re.split(r"[-/]", base)[0])                 # "Nashville-Davidson" is also just "Nashville"
            if base.lower().endswith(" city") and len(base) > 9:
                names.append(base[:-5])                                  # "Boise City" is also "Boise"
            for i, n in enumerate(names):
                key = J.place_key(n, st)
                if key:
                    yield key, (rank[0] + 3 * bool(i), rank[1]), lat, lng


def main():
    best = {}
    for path, kind in ((sys.argv[1], "place"), (sys.argv[2], "cousub")):
        for key, rank, lat, lng in rows(path, kind):
            if key not in best or rank < best[key][0]:
                best[key] = (rank, lat, lng)
    # the Census internal point of San Francisco (city and county) lies out at the Farallon Islands, 33 miles from downtown
    best["ca|san francisco"] = (best["ca|san francisco"][0], 37.77, -122.42)
    out = os.path.join(os.path.dirname(HERE), "us-places.tsv.gz")
    lines = "".join("%s\t%.2f\t%.2f\n" % (k, v[1], v[2]) for k, v in sorted(best.items()))
    with gzip.GzipFile(out, "wb", mtime=0) as f:
        f.write(lines.encode("utf-8"))
    print("%d places -> %s (%d bytes)" % (len(best), out, os.path.getsize(out)))


if __name__ == "__main__":
    main()
