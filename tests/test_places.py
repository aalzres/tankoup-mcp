import pytest

from tankoup_mcp.places import gazetteer, normalize


@pytest.fixture(scope="module")
def g():
    return gazetteer()


def test_the_gazetteer_covers_every_province(g):
    assert len(g.provinces) == 52
    assert len(g.municipalities) > 3000


def test_normalize_drops_accents_case_and_punctuation():
    assert normalize("  Cádiz, ESPAÑA ") == "cadiz espana"
    assert normalize("L'Alquería") == "l alqueria"


@pytest.mark.parametrize(("query", "label"), [
    ("Córdoba", "Córdoba"),
    ("cordoba", "Córdoba"),
    ("Lucena, Córdoba", "Lucena (Córdoba)"),
    ("Vigo (Pontevedra), Spain", "Vigo (Pontevedra)"),
    ("Móstoles, España", "Móstoles (Madrid)"),
    ("Alicante", "Alicante/Alacant (Alicante)"),
    ("Elx", "Elche/Elx (Alicante)"),
    ("San Sebastián", "Donostia-San Sebastián (Gipuzkoa)"),
    ("Palma", "Palma de Mallorca (Illes Balears)"),
    ("Seville", "Sevilla"),
    ("Barcelone", "Barcelona"),
])
def test_finds_towns_by_their_usual_names(g, query, label):
    best, _ = g.find_municipality(query)
    assert best is not None and best.label == label


def test_a_province_name_is_not_fuzzed_into_a_town(g):
    assert g.find_municipality("Asturias") == (None, [])
    assert g.find_province("Asturias").slug == "asturias"


def test_a_short_prefix_is_not_guessed(g):
    best, _ = g.find_municipality("Alcala")
    assert best is None
    assert any(s.startswith("Alcal") for s in g.suggestions("Alcala"))


@pytest.mark.parametrize(("query", "slug"), [
    ("Vizcaya", "bizkaia"),
    ("Valencia", "valencia-valencia"),
    ("València", "valencia-valencia"),
    ("Baleares", "illes-balears"),
    ("provincia de Cádiz", "cadiz"),
    ("Tenerife", "santa-cruz-de-tenerife"),
    ("Araba/Álava", "araba-alava"),
])
def test_finds_provinces_in_any_of_their_names(g, query, slug):
    assert g.find_province(query).slug == slug


def test_province_centre_sits_inside_the_province(g):
    madrid = g.provinces["madrid"]
    assert 40.0 < madrid.lat < 41.0 and -4.2 < madrid.lng < -3.3
