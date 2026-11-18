"""Catalogue validé Cellules SM (oct. 2026) — source de vérité du moteur.

Les totaux structurels (Somme codes, D+E+F+G) restent des formules Excel.
Les cellules « 0 – néant » n'ont pas de règle : elles ne sont pas forcées à 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.reporting_bcm_sm.engine.det_basis import (
    BASIS_CREDIT,
    BASIS_CREDIT_MINUS_DEBIT,
    BASIS_DEBIT,
    BASIS_NET,
)

ORIGIN_AUTO = "AUTO"
ORIGIN_MANUAL = "MANUAL"
ORIGIN_ADJUST = "AUTO_THEN_ADJUST"
ORIGIN_COPY = "COPY"
ORIGIN_PCT = "PCT"
ORIGIN_REMAINDER = "REMAINDER"

# Paramètres mensuels existants → cellules manuelles.
PARAM_TO_CELL = {
    "publics_mru": "A:322:D",
    "publics_dev": "A:322:F",
    "dat_public": "A:327:D",
    "amort_frais_immo": "A:234:C",
}
PROJETS_PARAM = "projets"
PCT_30 = Decimal("0.30")


@dataclass(frozen=True)
class Term:
    ncgs: tuple[str, ...] = ()
    ncg_class: str | None = None
    accounts: tuple[str, ...] = ()
    currency: str = "ALL"
    basis: str = BASIS_NET
    sign: int = 1


@dataclass(frozen=True)
class CellRule:
    key: str
    origin: str
    terms: tuple[Term, ...] = ()
    minus_cells: tuple[str, ...] = ()
    plus_cells: tuple[str, ...] = ()
    copy_from: tuple[str, ...] = ()
    pct: Decimal | None = None
    pct_sources: tuple[str, ...] = ()
    remainder_total: tuple[str, ...] = ()
    param_code: str | None = None
    minus_param: str | None = None
    plus_param: str | None = None
    notes: str = ""


def _t(
    *ncgs: str,
    basis: str = BASIS_NET,
    fx: bool = False,
    accounts: tuple[str, ...] = (),
    ncg_class: str | None = None,
    sign: int = 1,
) -> Term:
    return Term(
        ncgs=ncgs,
        ncg_class=ncg_class,
        accounts=accounts,
        currency="FX" if fx else "ALL",
        basis=basis,
        sign=sign,
    )


def _auto(key: str, *terms: Term, minus: tuple[str, ...] = (), plus: tuple[str, ...] = (), notes: str = "") -> CellRule:
    return CellRule(key=key, origin=ORIGIN_AUTO, terms=terms, minus_cells=minus, plus_cells=plus, notes=notes)


def _adj(
    key: str,
    *terms: Term,
    minus: tuple[str, ...] = (),
    plus: tuple[str, ...] = (),
    minus_param: str | None = None,
    plus_param: str | None = None,
    notes: str = "",
) -> CellRule:
    return CellRule(
        key=key,
        origin=ORIGIN_ADJUST,
        terms=terms,
        minus_cells=minus,
        plus_cells=plus,
        minus_param=minus_param,
        plus_param=plus_param,
        notes=notes,
    )


def _man(key: str, param: str | None = None, notes: str = "") -> CellRule:
    return CellRule(key=key, origin=ORIGIN_MANUAL, param_code=param, notes=notes)


def _copy(key: str, *sources: str, notes: str = "") -> CellRule:
    return CellRule(key=key, origin=ORIGIN_COPY, copy_from=sources, notes=notes)


def _pct(key: str, *sources: str, pct: Decimal = PCT_30, notes: str = "") -> CellRule:
    return CellRule(key=key, origin=ORIGIN_PCT, pct=pct, pct_sources=sources, notes=notes)


def _rem(key: str, *total: str, minus: tuple[str, ...] = (), notes: str = "") -> CellRule:
    return CellRule(key=key, origin=ORIGIN_REMAINDER, remainder_total=total, minus_cells=minus, notes=notes)


# --- ETAT A : 44 règles Balance + manuelles / ajustements ---
ETAT_A_RULES: tuple[CellRule, ...] = (
    _auto(
        "A:102:F",
        _t("100000", "100100", basis=BASIS_DEBIT, fx=True),
        notes="F9 caisse devises résidents — solde débiteur NCG 100000+100100 (hors MRU/MRO)",
    ),
    _auto("A:102:D", _t("100000", "100100"), minus=("A:102:F",), notes="D9 net − F9"),
    _auto("A:105:D", _t("110000")),
    _auto("A:109:G", _t("120000", "120010", "120020", basis=BASIS_DEBIT, fx=True)),
    _auto("A:110:G", _t("122000", basis=BASIS_DEBIT, fx=True)),
    _man("A:114:D", notes="D21 hors balance 150 M − 150 M"),
    _auto("A:126:D", _t("200000")),
    _auto("A:127:D", _t("201000", "201800", "204100")),
    _auto("A:128:D", _t("202000", "202200", "202400", "202800", "203000", "204200")),
    _auto("A:129:D", _t("203104", "203800", "204300")),
    _auto("A:131:C", _t("290000", "356000", basis=BASIS_CREDIT)),
    _auto(
        "A:131:D",
        _t(
            "210000",
            "210005",
            "210010",
            "210020",
            "210021",
            "210022",
            "210030",
            "210100",
            "210400",
            "211100",
            "211110",
            "211130",
            "216000",
            "216100",
            basis=BASIS_DEBIT,
        ),
        Term(ncgs=("211100", "211110", "211130"), basis=BASIS_CREDIT, sign=-1),
        minus=("A:131:C",),
        notes=(
            "D38 BCM 131 — Σ DEB 14 NCG − Σ CRE 211100+211110+211130 − C38. "
            "Montant métier uniquement. Aucun déséquilibre de bilan, aucun résiduel."
        ),
    ),
    _auto("A:132:D", _t("220100")),
    _auto("A:133:D", _t("230000")),
    _auto("A:134:D", _t("240100")),
    _auto(
        "A:201:D",
        _t(
            "102000",
            "110010",
            "180000",
            "301110",
            "311115",
            "311150",
            "315000",
            "316000",
            "316100",
            basis=BASIS_DEBIT,
        ),
    ),
    _auto(
        "A:206:D",
        _t(
            "120030",
            "218000",
            "218100",
            "218200",
            "320000",
            "320001",
            "322000",
            "323000",
            "323005",
            "323010",
            "323020",
            "323030",
            "323050",
            "323090",
            "323100",
            "323110",
            "324000",
            "326001",
            "326010",
            "326015",
            "326030",
            "326080",
            "326110",
            "350000",
            "325000",
            "352000",
            "352001",
            "359000",
            basis=BASIS_DEBIT,
        ),
        notes=(
            "D47 débiteurs divers — Σ DEB des 28 NCG. 218000 une seule fois. "
            "352000 et 352001. 320000, 320001, 322000, 323000, 323005, 323010 inclus. "
            "350000 ici, pas sur A:211:D. Aucune soustraction CRE."
        ),
    ),
    _auto(
        "A:211:D",
        _t(
            "351017",
            "351025",
            "351027",
            "351029",
            "351030",
            "351032",
            "351033",
            "351038",
            "351043",
            "351047",
            "351048",
            "351049",
            "351053",
            "351062",
            "351072",
            "351073",
            "351074",
            basis=BASIS_DEBIT,
        ),
        notes="D52 produits à recouvrir — Σ DEB 17 NCG (sans 350000 ni 351014 ; +351062). 350000 reste sur A:206:D.",
    ),
    _auto("A:216:D", _t("110200", "155000", basis=BASIS_DEBIT)),
    _auto("A:217:D", _t("383000", basis=BASIS_DEBIT)),
    _auto("A:219:D", _t("400000")),
    _auto("A:225:C", _t("482000", basis=BASIS_CREDIT)),
    _auto("A:225:D", _t("420000", basis=BASIS_DEBIT), minus=("A:225:C",)),
    _auto(
        "A:227:D",
        _t("453000", basis=BASIS_DEBIT),
        notes="NCG 453000 IMMO.EN COURS — solde débiteur (OUGUIYAS résidents)",
    ),
    _man("A:234:C", param="amort_frais_immo", notes="C75 split 487000"),
    _auto("A:234:D", _t("470000", basis=BASIS_DEBIT), minus=("A:234:C",)),
    _adj("A:235:C", _t("487000", basis=BASIS_CREDIT), minus=("A:234:C",), notes="C76 487000 − C75"),
    _auto("A:235:D", _t("475000", basis=BASIS_DEBIT), minus=("A:235:C",)),
    _auto("A:236:D", _t("511000", basis=BASIS_DEBIT)),
    _auto("A:304:G", _t("120000", basis=BASIS_CREDIT, fx=True)),
    _auto("A:306:D", _t("120200", basis=BASIS_CREDIT)),
    _auto("A:310:D", _t("126000", basis=BASIS_CREDIT)),
    _auto("A:313:G", _t("127001", basis=BASIS_CREDIT)),
    _man("A:322:D", param="publics_mru", notes="D106 publics MRU"),
    _man("A:322:F", param="publics_dev", notes="F106 publics devises"),
    _auto("A:323:F", _t("210000", "210010", basis=BASIS_CREDIT, fx=True), minus=("A:322:F",)),
    _auto("A:325:D", _t("210005", basis=BASIS_CREDIT)),
    _adj(
        "A:323:D",
        _t(
            "210000",
            "210005",
            "210010",
            "210020",
            "210021",
            "210022",
            "210030",
            "210100",
            "210400",
            basis=BASIS_CREDIT,
        ),
        minus=("A:322:D", "A:322:F", "A:323:F", "A:325:D"),
        minus_param=PROJETS_PARAM,
        notes="D107 − projets − 322 − F323 − 325",
    ),
    _man("A:327:D", param="dat_public", notes="D111 DAT public"),
    _auto("A:328:D", _t("215000", basis=BASIS_CREDIT), minus=("A:327:D",)),
    _auto("A:332:D", _t("216000", "216100", basis=BASIS_CREDIT)),
    _copy("A:331:D", "A:332:D", notes="épargne = livrets"),
    _copy("A:331:E", "A:332:E"),
    _copy("A:331:F", "A:332:F"),
    _copy("A:331:G", "A:332:G"),
    _auto("A:335:D", _t("218000", basis=BASIS_CREDIT)),
    _auto(
        "A:402:D",
        _t(
            "102000",
            "180000",
            "300000",
            "301110",
            "311115",
            "311150",
            "315000",
            "315100",
            "316000",
            "316100",
            basis=BASIS_CREDIT,
        ),
        notes=(
            "D122 clientèle exigible après encaissement — Σ CRE des 10 NCG. "
            "311115 et 315100 inclus. Aucune soustraction DEB."
        ),
    ),
    _adj(
        "A:403:D",
        _t(
            "120030",
            "218100",
            "218200",
            "218300",
            "320000",
            "320001",
            "322000",
            "323000",
            "323005",
            "323010",
            "323020",
            "323030",
            "323090",
            "323110",
            "324000",
            "326001",
            "326010",
            "326015",
            "326030",
            "326080",
            "352000",
            "352001",
            "359000",
            "323050",
            "323100",
            "326110",
            basis=BASIS_CREDIT,
        ),
        plus_param=PROJETS_PARAM,
        notes="D123 + projets ; −21 manuel",
    ),
    _auto(
        "A:408:D",
        _t(
            "351047",
            "354010",
            "354018",
            "354019",
            "354020",
            "354022",
            "354023",
            "354073",
            "355000",
            "355003",
            "351014",
            basis=BASIS_CREDIT,
        ),
    ),
    _auto("A:418:D", _t("520300", "552000", basis=BASIS_CREDIT)),
    _auto("A:422:D", _t("580000", basis=BASIS_CREDIT)),
    _auto("A:423:D", _t("590000", "590200", basis=BASIS_CREDIT)),
    _auto("A:425:D", _t("570000", basis=BASIS_CREDIT)),
    _auto(
        "A:426:D",
        _t(ncg_class="7", basis=BASIS_CREDIT_MINUS_DEBIT),
        Term(ncg_class="6", basis=BASIS_NET, sign=-1),
        _t(ncg_class="8", basis=BASIS_CREDIT_MINUS_DEBIT),
        _t("358000", basis=BASIS_CREDIT_MINUS_DEBIT),
        notes="résultat cl.7 − cl.6 + cl.8 + 358000",
    ),
    _auto("A:512:G", _t("903303", "922300", "922800", basis=BASIS_DEBIT, fx=True)),
    _auto(
        "A:516:G",
        _t("923840", basis=BASIS_DEBIT, fx=True, accounts=("00068120206",)),
        notes="G167 caution EUR",
    ),
    _auto(
        "A:516:D",
        _t(
            "923830",
            "923831",
            "923832",
            "923840",
            "923841",
            "923842",
            "923843",
            "923844",
            "923880",
            "923890",
            basis=BASIS_DEBIT,
        ),
        minus=("A:516:G",),
    ),
    _copy("A:520:D", "A:509:D"),
    _copy("A:520:E", "A:509:E"),
    _copy("A:520:F", "A:509:F"),
    _copy("A:520:G", "A:509:G"),
)

# ETAT B : copies A + 30 % privé (COD / immo / douteuses). Pas de fichier crédits.
ETAT_B_RULES: tuple[CellRule, ...] = (
    _copy("B:105:D", "A:126:D"),
    _copy("B:124:F", "A:127:D"),
    _copy("B:132:E", "A:128:D"),
    _copy("B:204:E", "A:129:D"),
    _copy("B:208:D", "A:132:D"),
    _pct("B:207:E", "A:131:C", "A:131:D", notes="COD privé 30 %"),
    _rem("B:207:D", "A:131:C", "A:131:D", minus=("B:207:E",)),
    _pct("B:209:E", "A:133:D", notes="immobilisées 30 %"),
    _rem("B:209:D", "A:133:D", minus=("B:209:E",)),
    _pct("B:210:E", "A:134:D", notes="douteuses 30 %"),
    _rem("B:210:D", "A:134:D", minus=("B:210:E",)),
    _copy("B:107:C", "B:108:C"),
    _copy("B:107:D", "B:108:D"),
    _copy("B:107:E", "B:108:E"),
    _copy("B:107:F", "B:108:F"),
    _copy("B:107:G", "B:108:G"),
    _copy("B:107:H", "B:108:H"),
    _rem("B:120:E", "A:512:D", minus=("B:120:D",), notes="A512 − EPC"),
)

# ETAT C : reprises A/B. 208=209 reste une formule du canevas (alerte double comptage).
ETAT_C_RULES: tuple[CellRule, ...] = (
    _copy("C:110:D", "B:105:D"),
    _copy("C:112:D", "B:124:F"),
    _copy("C:114:D", "B:132:E"),
    _copy("C:115:E", "B:204:E"),
    CellRule(key="C:203:E", origin=ORIGIN_COPY, copy_from=("A:313:D", "A:313:G"), notes="A313 MRU+Dev nres"),
    _copy("C:209:E", "A:326:H"),
    _copy("C:208:C", "C:209:C"),
    _copy("C:208:D", "C:209:D"),
    _copy("C:208:E", "C:209:E"),
)

INFO_RULES: tuple[CellRule, ...] = (
    _copy("INFO:C9", "A:426:D", notes="bénéfice = A426"),
)

ALL_RULES: tuple[CellRule, ...] = ETAT_A_RULES + ETAT_B_RULES + ETAT_C_RULES + INFO_RULES
RULES_BY_KEY: dict[str, CellRule] = {r.key: r for r in ALL_RULES}

MANUAL_KEYS = tuple(r.key for r in ALL_RULES if r.origin == ORIGIN_MANUAL)
ADJUST_KEYS = tuple(r.key for r in ALL_RULES if r.origin == ORIGIN_ADJUST)
AUTO_KEYS = tuple(r.key for r in ALL_RULES if r.origin == ORIGIN_AUTO)


def catalog_stats() -> dict[str, int]:
    return {
        "all": len(ALL_RULES),
        "auto": len(AUTO_KEYS),
        "manual": len(MANUAL_KEYS),
        "adjust": len(ADJUST_KEYS),
        "etat_a": len(ETAT_A_RULES),
        "etat_b": len(ETAT_B_RULES),
        "etat_c": len(ETAT_C_RULES),
    }
