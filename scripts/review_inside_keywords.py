"""Review of 'SoilVoc term inside a longer keyword' links (status soilvoc-partial).

Every (keyword, SoilVoc term) pair gets a verdict:
  same      keyword means the SoilVoc term itself -> can be promoted to a normal match
  narrower  keyword is a kind/aspect of the term  -> safe as a 'broader' link
  wrong     different meaning (lab method, gene, material, place, other sense) -> drop
  unclear   needs a person to decide
Default is 'narrower'; exceptions are listed below with a reason.
Writes curation/inside_keyword_review.csv
"""
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "reports" / "subjects_cleaned" / "subjects_cleaned.csv"
OUT = ROOT / "curation" / "inside_keyword_review.csv"

SAME = {  # (keyword, term) or keyword -> note
    "plant growth promoting rhizobacteria": "hyphen only",
    "nitrate nitrogen": "same term",
    "podzol soil": "same term",
    "soil phosphorus content": "same term",
    "soil nitrogen content": "same term",
    "plantio direto": "Portuguese for no-till",
    "pf wg kurve": "pF curve = water retention curve",
    "soil water retention curve": "same concept",
    "soil sciences not elsewhere classified": "ANZSRC field label",
    "soils soil science": "same term",
    "plastic mulch film": "same concept",
    "bonitate": "soil rating (Bonität)",
    "boniteet": "soil rating (Estonian)",
    "kakeff": "effective CEC abbreviation",
    "effektive kationenaustauschkapazitäten": "effective CEC",
    "zinkgehalt": "zinc content",
    "humusgehalt": "humus content",
    "torfarten": "peat types",
    "òxids de ferro": "iron oxides",
    "soil digital soil mapping": "duplicated word",
    "digital soil mapping techniques": "same concept",
    "bodenerosionsgefährdung": "soil erosion risk",
    "gestão sustentável do solo": "sustainable soil management",
    "gestion durable des sols": "sustainable soil management",
    "sustainable soil management": "kind of soil management",
    "landwirtschaftliche nutzung": "agricultural land use",
    "nutzung der landwirtschaftlichen fläche": "agricultural land use",
    "exploitation de la terre agricole": "agricultural land use",
    "начин коришћења земљишта": "Serbian for land use",
    "plan de utilizare a terenului": "Romanian land-use plan",
    "maankäytön suunnittelu": "Finnish land-use planning",
    "nutzart": "land-use type",
    "flurstücksnutzung": "parcel land use",
    "hauptbodennutzung": "main land use",
    "obszar badań gleby": "Polish soil survey area",
    "ocena jakości gleb": "Polish soil quality assessment",
    "bodemvochthuishouding": "Dutch soil moisture regime",
    "riserva idrica dei suoli": "Italian soil water reserve",
    "sòls humitat mesurament": "Catalan soil moisture measurement",
    "regim de umiditate a solului": "Romanian soil moisture regime",
    "mejora de suelos ácidos": "Spanish acid soil improvement",
    "carta de solos e de aptidão agrícola e florestal": "Portuguese soil map",
    "bodemkaart van belgië": "soil map of Belgium",
    "bodemkaartvannederland": "soil map of the Netherlands",
    "konzeptbodenkarte": "concept soil map",
    "zero artificialisation nette": "French policy on land take",
    "total soil loss": "soil loss", "soil loss ratio": "soil loss", "soil loss severity analysis": "soil loss",
    "field saturated hydraulic conductivity": "field-measured Ksat",
}
WRONG = {
    # lab / analytical methods, data handling
    "inductively coupled plasma optical emission spectrometry": "lab method (light emission)",
    "excitation emission matrix": "fluorescence method",
    "navigation aérienne centre d'émission et de réception radioélectrique communications électroniques": "radio emission",
    "vacuum filtration": "lab method; SoilVoc filtration is a soil function",
    "data filtration": "data processing",
    "peptide fragments": "molecular biology", "restriction fragment length": "molecular biology",
    "metagenome fragment recruitment": "bioinformatics", "metagenome fragment recruitments": "bioinformatics",
    "fragment recruitment": "bioinformatics",
    "lte excel input mask": "data entry form", "input data processing": "data processing",
    "energy input output": "energy accounting", "groundwater inputs": "hydrology, not farm inputs",
    "netto sedimentaanvoer naar de waterloop ongezuiverde riooluitlaten": "sewer discharge",
    "chemical precipitation": "chemistry; SoilVoc precipitation is rainfall",
    "microbially induced calcite precipitation": "chemistry; SoilVoc precipitation is rainfall",
    # biology (genes, proteins, signalling)
    "calcium calmodulin dependent protein kinases": "protein", "calcium signalling": "cell signalling",
    "calcium signaling": "cell signalling", "potassium channels": "ion channel", "iron regulatory proteins": "protein",
    "zinc transporter": "gene/protein", "molybdenum nitrogenase": "enzyme",
    "reactive oxygen and nitrogen species": "cell stress biology", "pyridinic nitrogen": "carbon materials chemistry",
    "spider mites": "plant pest; SoilVoc mites are soil mesofauna",
    # materials, engineering, history
    "vanadium carbide": "materials science", "aluminium alloy": "metallurgy",
    "green sand casting": "metal casting", "graphene oxide gras": "materials (GRAS)",
    "refined grass fibers": "fibre material", "carbonate rock ashlars": "building stone",
    "iberian iron age sanctuary": "archaeology (Iron Age)", "iron age": "archaeology (Iron Age)",
    "structure soil structure interaction": "geotechnics: soil-structure interaction",
    "structure soil structure interactions": "geotechnics: soil-structure interaction",
    "kinematic soil structure interaction": "geotechnics: soil-structure interaction",
    "structure soil structure interaction multiple scattering shear horizontal waves green’s functions": "geotechnics",
    "biomass to liquids": "bioenergy",
    "organic soil improver": "amendment, not organic soils",
    "soc:clay ratio": "not the SoilVoc clay ratio index",
    "institute of soil science and plant cultivation": "organisation name",
    "soil information officer": "job title",
    "incremental evapo transpiration": "should be evapotranspiration, not transpiration",
    "evaporation transpiration": "should be evapotranspiration, not transpiration",
}
PAIR_WRONG = {  # only one of several terms is wrong
    ("metal matrix composites life cycle assessment low pressure die casting green sand casting", "aluminium"): "metallurgy",
    ("metal matrix composites life cycle assessment low pressure die casting green sand casting", "sand"): "metal casting",
    ("agricultural soil science", "agricultural soils"): "field of science, not a soil type",
    ("calcium carbonate", "calcium"): "compound; carbonate link is enough",
    ("clay loam soil", "clay"): "texture class; loam soils link is enough",
}
UNCLEAR = {
    "loess plateau": "place name", "the loess plateau": "place name", "loess region in shanxi province": "place name",
    "feinbodenform": "German data field", "riverbank filtration": "water treatment through soil",
    "sand boil": "geotechnical phenomenon", "sand and dust storm": "aeolian, not soil particle",
    "sand inoculation": "lab substrate", "kiesabbau": "gravel mining", "kiesgewinnung": "gravel mining",
    "gypsum mining": "mining", "gypsum crystallization water": "chemistry",
    "soil pore water": "pore water = soil solution", "soil resource acquisition": "plant ecology",
    "nitrogen dioxide": "air pollutant", "nitrogen oxides": "air pollutant",
    "zinc sensor": "chemical sensor", "zinc sulfide": "compound", "surface modified clay": "material",
    "nanoparticulate vivianite mercury": "chemistry", "seawater iron content": "marine",
    "environmental sciences related to agriculture and land use": "category label",
    "aménagement du territoire": "spatial planning, broader than land use",
    "planos especiais de ordenamento do território": "spatial planning",
    "soil flood": "unclear phrase", "clay perdition": "unclear phrase",
    "computation of total soil organic carbon stock and its standard deviation from layered soils": "title as keyword",
    "ultra high performance liquid chromatography high resolution mass spectrometry ion mobility": "long multi-topic keyword",
    "indoor air quality and health effects": "indoor air",
    "biomass c": "plant or soil biomass?", "biomass carbon": "plant or soil biomass?",
    "contaminated biomass": "plant biomass", "contaminated biomass feedstock": "plant biomass",
    "μολυσμένη βιομάζα": "plant biomass",
    "phytoremediation contaminated biomass postharvest management metal recovery heavy metals": "plant biomass",
    "snow experiments": "snow manipulation?", "snow experiment": "snow manipulation?",
}
# SoilVoc 'biomass' is under 'soil biota': plant / energy biomass is the wrong sense.
SOIL_BIOMASS = ("microbial", "microbiana", "fungal")


def verdict(kw, term):
    for table, v in ((PAIR_WRONG, "wrong"),):
        if (kw, term) in table:
            return v, table[(kw, term)]
    for k, v in ((SAME, "same"), (WRONG, "wrong"), (UNCLEAR, "unclear")):
        for key, note in k.items():
            if kw == key or (len(key) > 60 and kw.startswith(key[:60])):
                return v, note
    if term == "biomass":
        if any(w in kw for w in SOIL_BIOMASS):
            return "narrower", "soil biota biomass"
        return "wrong", "plant/energy biomass; SoilVoc biomass is under soil biota"
    return "narrower", ""


pairs = defaultdict(lambda: [0, ""])
for r in csv.DictReader(open(SRC)):
    if r["status"] != "soilvoc-partial":
        continue
    for term, uri in zip(r["soilvoc_label"].split("; "), r["soilvoc_uri"].replace("; ", " | ").split(" | ")):
        p = pairs[(r["cleaned"], term)]
        p[0] += int(r["records"] or 0)
        p[1] = uri

rows = []
for (kw, term), (n, uri) in pairs.items():
    v, note = verdict(kw, term)
    rows.append({"keyword": kw, "soilvoc_term": term, "records": n, "verdict": v, "note": note, "soilvoc_uri": uri})
rows.sort(key=lambda r: (["same", "narrower", "unclear", "wrong"].index(r["verdict"]), -r["records"], r["keyword"]))
with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

tot = defaultdict(lambda: [0, 0])
for r in rows:
    tot[r["verdict"]][0] += 1
    tot[r["verdict"]][1] += r["records"]
print("pairs", len(rows), {k: v for k, v in tot.items()})
