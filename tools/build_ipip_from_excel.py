#!/usr/bin/env python3
"""Generate OSD files for IPIP instruments from the Tedone item assignment Excel file.

Reads: Downloads/TedoneItemAssignmentTable30APR21.xlsx
       (columns: instrument, alpha, key, text, label)

Writes: scales/ipip/{CODE}/{CODE}.osd   for each new instrument/subscale

Rules:
  - instruments with ≤50 total items → one multi-dimension OSD file
  - instruments with >50 total items → one OSD file per subscale (dimension)
  - Each scale gets both _sum and _mean scoring dimensions
  - Items already covered by hand-crafted OSD files are skipped (SKIP_INSTRUMENTS)

Usage:
    python3 tools/build_ipip_from_excel.py [--force] [--instrument NAME]

Options:
    --force         Overwrite existing OSD files
    --instrument    Only process this instrument (e.g. "HPI")
    --dry-run       Print what would be created without writing
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict, OrderedDict
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.exit("openpyxl not installed. Run: pip install openpyxl")

REPO_ROOT       = Path(__file__).parent.parent
SCALES_DIR      = REPO_ROOT / "scales" / "ipip"
TRANS_DIR       = SCALES_DIR / "translations"
EXCEL_PATH      = Path.home() / "Downloads" / "TedoneItemAssignmentTable30APR21.xlsx"
ITEM_CODES_PATH = SCALES_DIR / "ipip_item_codes.json"
MASTER_TRANS    = TRANS_DIR / "ipip_master_en.json"   # master English translation file

# Shared translation keys for IPIP likert anchors (used by all IPIP OSD files)
IPIP_LIKERT_KEYS = ["ipip_likert_1", "ipip_likert_2", "ipip_likert_3", "ipip_likert_4", "ipip_likert_5"]
IPIP_SHARED_EN = {
    "ipip_likert_1": "Very Inaccurate",
    "ipip_likert_2": "Moderately Inaccurate",
    "ipip_likert_3": "Neither Accurate Nor Inaccurate",
    "ipip_likert_4": "Moderately Accurate",
    "ipip_likert_5": "Very Accurate",
    "ipip_question_head": (
        "<h3>How Accurately Can You Describe Yourself?</h3>"
        "<p>Describe yourself as you generally are now, not as you wish to be in the future. "
        "Describe yourself as you honestly see yourself, in relation to other people you know "
        "of the same sex as you are, and roughly your same age. So that you can describe "
        "yourself in an honest manner, your responses will be kept in absolute confidence. "
        "Indicate the accuracy of the item as it applies to you, using the following rating scale:</p>"
    ),
    "ipip_debrief": "Thank you for completing this questionnaire.",
}


def load_item_codes() -> dict:
    """Load text→IPIP_code mapping from ipip_item_codes.json. Returns {} if not found."""
    if ITEM_CODES_PATH.exists():
        data = json.loads(ITEM_CODES_PATH.read_text(encoding='utf-8'))
        return data.get('text_to_code', {})
    return {}


def text_to_key(text: str, text_to_code: dict) -> str:
    """Convert item text to a canonical translation key.

    Uses the IPIP alphanumeric code (e.g. ipip_H1131) when known,
    otherwise falls back to a slugified form (ipip_text_<slug>).
    """
    code = text_to_code.get(text.strip())
    if code:
        return f"ipip_{code}"
    # Fallback: deterministic slug from text
    slug = re.sub(r'[^a-z0-9]+', '_', text.lower().strip()).strip('_')[:40]
    return f"ipip_text_{slug}"

# Instruments already fully implemented by hand — skip to avoid overwriting
SKIP_INSTRUMENTS = {
    '16PF', 'BFAS', 'BIDR', 'BIS_BAS', 'CAT-PD', 'HEXACO_PI',
    'IPIP-IPC', 'NEO', 'ORVIS', 'VIA',
    'Cacioppo1982',   # IPIP-NFC
    'Radloff1977',    # IPIP-Depression
    'Rosenberg1965',  # IPIP-SelfEsteem
    'Snyder1974',     # IPIP-SelfMonitoring
    'Span2002',       # IPIP-ADHD
    # BFAS-20 is partially implemented; skip for now
    'BFAS-20',
}

# Items threshold for splitting into per-subscale files
SPLIT_THRESHOLD = 50

# Short name prefix for split instruments (used in OSD name field instead of full instrument name)
# Format: instrument_key → short prefix used in "IPIP XXX: ScaleName"
INSTRUMENT_SHORT_PREFIX = {
    'CPI':      'IPIP CPI',
    'HPI':      'IPIP HPI',
    'HPI-HIC':  'IPIP HPI-HIC',
    'JPI':      'IPIP JPI',
    'TCI':      'IPIP TCI',
    '6FPQ':     'IPIP 6FPQ',
    'MPQ':      'IPIP MPQ',
    '7FACTOR':  'IPIP 7-Factor',
    'AB5C':     'IPIP AB5C',
    'ORAIS':    'IPIP ORAIS',
    'NEO5-20':  'IPIP NEO5-20',
    'Barchard2001': 'IPIP EI',
    'Levenson1981': 'IPIP LOC',
    'HEXACO_PI': 'IPIP HEXACO',
}

# Official subscale abbreviations: (instrument, label_substring) → abbrev
# Used to build OSD code suffix and abbreviation field.
# Label matching is case-insensitive substring match.
SUBSCALE_ABBREVS = {
    # JPI — labels as they appear in Excel
    ('JPI', 'Intellectual-Complexity'):     'Cpx',
    ('JPI', 'Intellectual-Breadth'):        'Bdi',
    ('JPI', 'Ingenuity'):                   'Inv',
    ('JPI', 'Tolerance'):                   'Tol',
    ('JPI', 'Empathy'):                     'Emp',
    ('JPI', 'Anxiety'):                     'Axy',
    ('JPI', 'Conformity'):                  'Cpr',
    ('JPI', 'Sociability'):                 'Soc',
    ('JPI', 'Social-confidence'):           'Scf',
    ('JPI', 'Activity-Level'):              'Enl',
    ('JPI', 'Machiavellianism'):            'Sas',
    ('JPI', 'Risk-taking'):                 'Rkt',
    ('JPI', 'Organization'):                'Org',
    ('JPI', 'Traditionalism'):              'Trv',
    ('JPI', 'Responsibility'):              'Rsy',
    # TCI (labels matched to exact Excel column values)
    ('TCI', 'Variety-seeking'):             'NS1',
    ('TCI', 'Recklessness'):                'NS2',
    ('TCI', 'Extravagance'):                'NS3',
    ('TCI', 'Rebelliousness'):              'NS4',
    ('TCI', 'Neuroticism'):                 'HA1',
    ('TCI', 'Harm-Avoidance'):              'HA2',
    ('TCI', 'Social-discomfort'):           'HA3',
    ('TCI', 'Self-efficacy'):               'HA4',
    ('TCI', 'Sentimentality'):              'RD1',
    ('TCI', 'Friendliness'):                'RD2',
    ('TCI', 'Self-disclosure'):             'RD3',
    ('TCI', 'Conformity'):                  'RD4',
    ('TCI', 'Initiative'):                  'P1',
    ('TCI', 'Competence'):                  'P2',
    ('TCI', 'Achievement-striving'):        'P3',
    ('TCI', 'Industriousness'):             'P4',
    ('TCI', 'Satisfaction'):                'S1',
    ('TCI', 'Hope/Optimism'):               'S2',
    ('TCI', 'Resourcefulness'):             'S3',
    ('TCI', 'Self-acceptance'):             'S4',
    ('TCI', 'Impulse-Control'):             'S5',
    ('TCI', 'Tolerance'):                   'C1',
    ('TCI', 'Empathy'):                     'C2',
    ('TCI', 'Trust'):                       'C3',
    ('TCI', 'Compassion'):                  'C4',
    ('TCI', 'Morality'):                    'C5',
    ('TCI', 'Imagination'):                 'ST1',
    ('TCI', 'Romanticism'):                 'ST2',
    ('TCI', 'Conservatism'):                'ST4',
    ('TCI', 'Femininity'):                  'ST5',
    # 6FPQ
    ('6FPQ', 'Gregariousness'):             'EX1',
    ('6FPQ', 'Leadership'):                 'EX2',
    ('6FPQ', 'Exhibitionism'):              'EX3',
    ('6FPQ', 'Docility'):                   'AG1',
    ('6FPQ', 'Calmness'):                   'AG2',
    ('6FPQ', 'Adaptability'):               'AG3',
    ('6FPQ', 'Conservatism'):               'ME1',
    ('6FPQ', 'Deliberateness'):             'ME2',
    ('6FPQ', 'Orderliness'):                'ME3',
    ('6FPQ', 'Reclusiveness'):              'IP1',
    ('6FPQ', 'Unpretentiousness'):          'IP2',
    ('6FPQ', 'Self-Sufficiency'):           'IP3',
    ('6FPQ', 'Adventurousness'):            'OP1',
    ('6FPQ', 'Comprehension'):              'OP2',
    ('6FPQ', 'Culture'):                    'OP3',
    ('6FPQ', 'Achievement-striving'):       'IT1',
    ('6FPQ', 'Resourcefulness'):            'IT2',
    ('6FPQ', 'Humor'):                      'IT3',
    # Higher-level 6FPQ factors
    ('6FPQ', 'Extraversion'):               'EX',
    ('6FPQ', 'Agreeableness'):              'AG',
    ('6FPQ', 'Methodicalness'):             'ME',
    ('6FPQ', 'Independence'):               'IP',
    ('6FPQ', 'Intellectual Openness'):      'OP',
    ('6FPQ', 'Industriousness'):            'IT',
    # MPQ — labels as they appear in Excel
    ('MPQ', 'Joyfulness'):                  'WB',
    ('MPQ', 'Assertiveness'):               'SP',
    ('MPQ', 'Achievement-striving'):        'AC',
    ('MPQ', 'Friendliness'):                'SC',
    ('MPQ', 'Neuroticism'):                 'SR',
    ('MPQ', 'Belligerence'):                'AG',
    ('MPQ', 'Distrust'):                    'AL',
    ('MPQ', 'Planfulness'):                 'CO',
    ('MPQ', 'Risk-avoidance'):              'HA',
    ('MPQ', 'Conservatism'):                'TR',
    ('MPQ', 'Imagination'):                 'AB',
    ('MPQ', 'Unlikely Virtues'):            'UV',
    # 7FACTOR — Saucier (2009) abbreviations from IPIP source
    ('7FACTOR', 'Extraversion'):            'EXT',
    ('7FACTOR', 'Agreeableness'):           'AGR',
    ('7FACTOR', 'Conscientiousness'):       'CON',
    ('7FACTOR', 'Emotional Stability'):     'ES',
    ('7FACTOR', 'Intellect'):               'INT',
    ('7FACTOR', 'Attractiveness'):          'ATT',
    ('7FACTOR', 'Negative-Valence'):        'NV',
    # CPI — official CPI abbreviations matched to Goldberg's Excel label names
    ('CPI', 'Dominance'):                   'Do',
    ('CPI', 'Sociability'):                 'Sy',
    ('CPI', 'Social Presence'):             'Sp',
    ('CPI', 'Self-Acceptance'):             'Sa',
    ('CPI', 'Independence'):                'In',
    ('CPI', 'Empathy'):                     'Em',
    ('CPI', 'Responsibility'):              'Re',
    ('CPI', 'Socialization'):               'So',
    ('CPI', 'Self-control'):                'Sc',
    ('CPI', 'Good Nature'):                 'Gi',   # Good Impression proxy
    ('CPI', 'Amiability'):                  'Ami',
    ('CPI', 'Well-being'):                  'Wb',
    ('CPI', 'Tolerance'):                   'To',
    ('CPI', 'Competence'):                  'Ac',   # Achievement via Conformance
    ('CPI', 'Insight'):                     'Ai',   # Achievement via Independence
    ('CPI', 'Comprehension'):               'Ie',   # Intellectual Efficiency
    ('CPI', 'Adventurousness'):             'Fx',   # Flexibility
    ('CPI', 'Assertiveness'):               'Mp',   # Managerial Potential proxy
    ('CPI', 'Forcefulness'):                'Frc',
    ('CPI', 'Liberalism'):                  'Lib',
    ('CPI', 'Leadership'):                  'Lp',
    ('CPI', 'Planfulness'):                 'Pln',
    ('CPI', 'Poise'):                       'Po',
    ('CPI', 'Complexity'):                  'Cpx',
    ('CPI', 'Depth'):                       'Dep',
    ('CPI', 'Stability'):                   'Stb',
    ('CPI', 'Calmness'):                    'Clm',
    ('CPI', 'Security'):                    'Sec',
    ('CPI', 'Happiness'):                   'Hap',
    ('CPI', 'Politeness'):                  'Pol',
    ('CPI', 'Dutifulness'):                 'Dut',
    ('CPI', 'Self-discipline'):             'Sdi',
    ('CPI', 'Self-efficacy'):               'Sef',
    ('CPI', 'Temperance'):                  'Tmp',
    ('CPI', 'Timidity'):                    'Tim',
    ('CPI', 'Disorderliness'):              'Dis',
    ('CPI', 'Introversion'):                'Itn',
    ('CPI', 'Sentimentality'):              'Snt',
    ('CPI', 'Hope'):                        'Hop',
    # AB5C — short mnemonic codes (no official 2-3 char codes; Roman numeral system unusable in paths)
    ('AB5C', 'Gregariousness'):             'Grg',
    ('AB5C', 'Friendliness'):               'Frl',
    ('AB5C', 'Assertiveness'):              'Ast',
    ('AB5C', 'Poise'):                      'Poi',
    ('AB5C', 'Leadership'):                 'Ldr',
    ('AB5C', 'Talkativeness'):              'Tlk',
    ('AB5C', 'Sociability'):                'Soc',
    ('AB5C', 'Provocativeness'):            'Prv',
    ('AB5C', 'Warmth'):                     'Wrm',
    ('AB5C', 'Pleasantness'):               'Pls',
    ('AB5C', 'Empathy'):                    'Emp',
    ('AB5C', 'Cooperation'):                'Coo',
    ('AB5C', 'Sympathy'):                   'Sym',
    ('AB5C', 'Tenderness'):                 'Tnd',
    ('AB5C', 'Nurturance'):                 'Nur',
    ('AB5C', 'Conscientiousness'):          'Con',
    ('AB5C', 'Orderliness'):                'Ord',
    ('AB5C', 'Dutifulness'):                'Dut',
    ('AB5C', 'Purposefulness'):             'Pur',
    ('AB5C', 'Cautiousness'):               'Cau',
    ('AB5C', 'Moderation'):                 'Mod',
    ('AB5C', 'Organization'):               'Org',
    ('AB5C', 'Efficiency'):                 'Eff',
    ('AB5C', 'Perfectionism'):              'Prf',
    ('AB5C', 'Morality'):                   'Mor',
    ('AB5C', 'Stability'):                  'Stb',
    ('AB5C', 'Happiness'):                  'Hap',
    ('AB5C', 'Calmness'):                   'Clm',
    ('AB5C', 'Imperturbability'):           'Imp',
    ('AB5C', 'Tranquility'):                'Trq',
    ('AB5C', 'Cool-headedness'):            'Cht',
    ('AB5C', 'Toughness'):                  'Tgh',
    ('AB5C', 'Intellect'):                  'Int',
    ('AB5C', 'Depth'):                      'Dep',
    ('AB5C', 'Ingenuity'):                  'Ing',
    ('AB5C', 'Reflection'):                 'Ref',
    ('AB5C', 'Rationality'):                'Rat',
    ('AB5C', 'Creativity'):                 'Crt',
    ('AB5C', 'Imagination'):                'Img',
    ('AB5C', 'Quickness'):                  'Qck',
    ('AB5C', 'Understanding'):              'Und',
    ('AB5C', 'Competence'):                 'Cmp',
    ('AB5C', 'Introspection'):              'Isp',
    ('AB5C', 'Self-disclosure'):            'Sdc',
    ('AB5C', 'Modesty'):                    'Mds',
    # HPI — short 3-letter codes (no official IPIP abbreviations)
    ('HPI', 'Stability'):                   'Stb',
    ('HPI', 'Leadership'):                  'Ldr',
    ('HPI', 'Sociability'):                 'Soc',
    ('HPI', 'Friendliness'):                'Frl',
    ('HPI', 'Dutifulness'):                 'Dut',
    ('HPI', 'Creativity'):                  'Crt',
    ('HPI', 'Quickness'):                   'Qck',
    ('HPI', 'Calmness'):                    'Clm',
    ('HPI', 'Competence'):                  'Cmp',
    ('HPI', 'Cooperation'):                 'Coo',
    ('HPI', 'Gregariousness'):              'Grg',
    ('HPI', 'Happiness'):                   'Hap',
    ('HPI', 'Toughness'):                   'Tgh',
    # HPI-HIC — short codes keyed to HPI hierarchy
    ('HPI-HIC', 'Achievement-striving'):                    'Ach',
    ('HPI-HIC', 'Aesthetic Appreciation'):                  'Aes',
    ('HPI-HIC', 'Appearance-Consciousness'):                'App',
    ('HPI-HIC', 'Calmness'):                               'Clm',
    ('HPI-HIC', 'Conformity'):                              'Cnf',
    ('HPI-HIC', 'Cool-headedness'):                        'Coo',
    ('HPI-HIC', 'Curiosity'):                              'Cur',
    ('HPI-HIC', 'Dutifulness'):                            'Dut',
    ('HPI-HIC', 'Empathy'):                                'Emp',
    ('HPI-HIC', 'Exhibitionism'):                          'Exh',
    ('HPI-HIC', 'Forgiveness'):                            'For',
    ('HPI-HIC', 'Gregariousness'):                         'Grg',
    ('HPI-HIC', 'Happiness'):                              'Hap',
    ('HPI-HIC', 'Humor'):                                  'Hum',
    ('HPI-HIC', 'Impulse-Control'):                        'Ipc',
    ('HPI-HIC', 'Intellect'):                              'Int',
    ('HPI-HIC', 'Interest in Game'):                       'Gam',
    ('HPI-HIC', 'Introspection'):                          'Isp',
    ('HPI-HIC', 'Language Mastery'):                       'Lng',
    ('HPI-HIC', 'Leadership'):                             'Ldr',
    ('HPI-HIC', 'Love of Reading'):                        'Rdg',
    ('HPI-HIC', 'Orderliness'):                            'Ord',
    ('HPI-HIC', 'Organization'):                           'Org',
    ('HPI-HIC', 'Pleasantness'):                           'Pls',
    ('HPI-HIC', 'Problem-solving'):                        'Prb',
    ('HPI-HIC', 'Risk-taking'):                            'Rsk',
    ('HPI-HIC', 'Rumination'):                             'Rum',
    ('HPI-HIC', 'Security'):                               'Sec',
    ('HPI-HIC', 'Self-acceptance'):                        'Sac',
    ('HPI-HIC', 'Self-confidence'):                        'Scf',
    ('HPI-HIC', 'Self-discipline'):                        'Sdi',
    ('HPI-HIC', 'Sensitivity'):                            'Sns',
    ('HPI-HIC', 'Sociability'):                            'Soc',
    ('HPI-HIC', 'Social-confidence'):                      'Scn',
    ('HPI-HIC', 'Toughness'):                              'Tgh',
    ('HPI-HIC', 'Trust'):                                  'Trs',
    ('HPI-HIC', 'Variety-seeking'):                        'Var',
    ('HPI-HIC', 'Vitality'):                               'Vit',
    # VIA — 3-letter codes from Peterson & Seligman (2004) / IPIP source
    ('VIA', 'Aesthetic'):                   'App',
    ('VIA', 'Bravery'):                     'Bra',
    ('VIA', 'Capacity for Love'):           'Cap',
    ('VIA', 'Creativity'):                  'Crt',
    ('VIA', 'Curiosity'):                   'Cur',
    ('VIA', 'Equity'):                      'Equ',
    ('VIA', 'Forgiveness'):                 'For',
    ('VIA', 'Gratitude'):                   'Gra',
    ('VIA', 'Honesty'):                     'Hon',
    ('VIA', 'Hope'):                        'Hop',
    ('VIA', 'Humor'):                       'Hum',
    ('VIA', 'Industriousness'):             'Ind',
    ('VIA', 'Judgment'):                    'Jud',
    ('VIA', 'Kindness'):                    'Kin',
    ('VIA', 'Leadership'):                  'Lea',
    ('VIA', 'Love of Learning'):            'Lov',
    ('VIA', 'Modesty'):                     'Mod',
    ('VIA', 'Prudence'):                    'Pru',
    ('VIA', 'Self-control'):                'Sel',
    ('VIA', 'Social'):                      'Soc',
    ('VIA', 'Spirituality'):                'Spi',
    ('VIA', 'Teamwork'):                    'Cit',
    ('VIA', 'Vitality'):                    'Zes',
    ('VIA', 'Wisdom'):                      'Wis',
}

# Per-instrument metadata: (osd_code_prefix, full_name, abbreviation, domain, url, citation)
INSTRUMENT_META = {
    '6FPQ': (
        'IPIP-6FPQ', 'IPIP Six-Factor Personality Questionnaire', 'IPIP-6FPQ',
        'Personality',
        'https://ipip.ori.org/new6FPQKey.htm',
        'Jackson, D. N., Ashton, M. C., & Tomes, J. L. (1996). The six-factor model of personality: Facets from the Big Five. Personality and Individual Differences, 21(3), 391–402. https://doi.org/10.1016/0191-8869(96)00083-5',
    ),
    '7FACTOR': (
        'IPIP-7FACTOR', 'IPIP Seven-Factor Personality Scale', 'IPIP-7F',
        'Personality',
        'https://ipip.ori.org/new7factorKey.htm',
        'Tellegen, A., & Waller, N. G. (2008). Exploring personality through test construction: Development of the Multidimensional Personality Questionnaire. In G. J. Boyle, G. Matthews, & D. H. Saklofske (Eds.), The SAGE Handbook of Personality Theory and Assessment (Vol. 2, pp. 261–292). SAGE.',
    ),
    'AB5C': (
        'IPIP-AB5C', 'IPIP Abridged Big Five Circumplex', 'IPIP-AB5C',
        'Personality',
        'https://ipip.ori.org/newAB5CKeys.htm',
        'Hofstee, W. K. B., de Raad, B., & Goldberg, L. R. (1992). Integration of the Big Five and circumplex approaches to trait structure. Journal of Personality and Social Psychology, 63(1), 146–163. https://doi.org/10.1037/0022-3514.63.1.146',
    ),
    'Barchard2001': (
        'IPIP-EI', 'IPIP Emotional Intelligence Scale', 'IPIP-EI',
        'Personality',
        'https://ipip.ori.org/newKey4Barchard2001EI.htm',
        'Barchard, K. A. (2001). Emotional and social intelligence: Examining its place in the nomological network. Unpublished doctoral dissertation, University of British Columbia.',
    ),
    'Buss1980': (
        'IPIP-Buss', 'IPIP Self-Consciousness Scale', 'IPIP-SC',
        'Personality',
        'https://ipip.ori.org/newKey4Buss1980.htm',
        'Buss, A. H. (1980). Self-consciousness and social anxiety. Freeman.',
    ),
    'Chapman1986': (
        'IPIP-Chapman', 'IPIP Chapman Scales', 'IPIP-Chapman',
        'Mental Health',
        'https://ipip.ori.org/newKey4Chapman1986.htm',
        'Chapman, L. J., Chapman, J. P., & Raulin, M. L. (1976). Scales for physical and social anhedonia. Journal of Abnormal Psychology, 85(4), 374–382. https://doi.org/10.1037/0021-843X.85.4.374',
    ),
    'CPI': (
        'IPIP-CPI', 'IPIP California Psychological Inventory', 'IPIP-CPI',
        'Personality',
        'https://ipip.ori.org/newCPIKey.htm',
        'Gough, H. G. (1987). California Psychological Inventory administrator\'s guide. Consulting Psychologists Press.',
    ),
    'Foa1998': (
        'IPIP-Foa1998', 'IPIP Foa Interpersonal Scales (1998)', 'IPIP-Foa98',
        'Personality',
        'https://ipip.ori.org/newKey4Foa1998.htm',
        'Foa, U. G., & Foa, E. B. (1974). Societal structures of the mind. Charles C Thomas.',
    ),
    'Foa2002': (
        'IPIP-Foa2002', 'IPIP Foa Interpersonal Scales (2002)', 'IPIP-Foa02',
        'Personality',
        'https://ipip.ori.org/newKey4Foa2002.htm',
        'Foa, U. G., & Foa, E. B. (1974). Societal structures of the mind. Charles C Thomas.',
    ),
    'Goldberg1999': (
        'IPIP-Big5-31', 'IPIP Big Five Factor Markers (31-item)', 'IPIP-31',
        'Personality',
        'https://ipip.ori.org/newBigFive5broadKey.htm',
        'Goldberg, L. R. (1999). A broad-bandwidth, public-domain, personality inventory measuring the lower-level facets of several five-factor models. In I. Mervielde, I. Deary, F. De Fruyt, & F. Ostendorf (Eds.), Personality Psychology in Europe (Vol. 7, pp. 7–28). Tilburg University Press.',
    ),
    'Hoyle2002': (
        'IPIP-BriefSelfControl', 'IPIP Brief Self-Control Scale', 'IPIP-BSC',
        'Self & Coping',
        'https://ipip.ori.org/newKey4Hoyle2002.htm',
        'Tangney, J. P., Baumeister, R. F., & Boone, A. L. (2004). High self-control predicts good adjustment, less pathology, better grades, and interpersonal success. Journal of Personality, 72(2), 271–324. https://doi.org/10.1111/j.0022-3506.2004.00263.x',
    ),
    'HPI': (
        'IPIP-HPI', 'IPIP Hogan Personality Inventory', 'IPIP-HPI',
        'Personality',
        'https://ipip.ori.org/newHPIKey.htm',
        'Hogan, R., & Hogan, J. (1992). Hogan Personality Inventory manual. Hogan Assessment Systems.',
    ),
    'HPI-HIC': (
        'IPIP-HPIHIC', 'IPIP Hogan Personality Inventory — Homogeneous Item Composites', 'IPIP-HIC',
        'Personality',
        'https://ipip.ori.org/newHPIHICKey.htm',
        'Hogan, R., & Hogan, J. (1992). Hogan Personality Inventory manual. Hogan Assessment Systems.',
    ),
    'JPI': (
        'IPIP-JPI', 'IPIP Jackson Personality Inventory', 'IPIP-JPI',
        'Personality',
        'https://ipip.ori.org/newJPIKey.htm',
        'Jackson, D. N. (1994). Jackson Personality Inventory — Revised manual. Sigma Assessment Systems.',
    ),
    'Levenson1981': (
        'IPIP-Levenson', 'IPIP Levenson Locus of Control Scales', 'IPIP-Lev',
        'Personality',
        'https://ipip.ori.org/newKey4Levenson1981.htm',
        'Levenson, H. (1981). Differentiating among internality, powerful others, and chance. In H. M. Lefcourt (Ed.), Research with the locus of control construct (Vol. 1, pp. 15–63). Academic Press.',
    ),
    'MPQ': (
        'IPIP-MPQ', 'IPIP Multidimensional Personality Questionnaire', 'IPIP-MPQ',
        'Personality',
        'https://ipip.ori.org/newMPQKey.htm',
        'Tellegen, A., & Waller, N. G. (2008). Exploring personality through test construction: Development of the Multidimensional Personality Questionnaire. In G. J. Boyle, G. Matthews, & D. H. Saklofske (Eds.), The SAGE Handbook of Personality Theory and Assessment (Vol. 2, pp. 261–292). SAGE.',
    ),
    'NEO5-20': (
        'IPIP-NEO5-20', 'IPIP NEO Five-Factor Inventory (20-item)', 'IPIP-NEO-20',
        'Personality',
        'https://ipip.ori.org/newNEOKey.htm',
        'Costa, P. T., Jr., & McCrae, R. R. (1992). Revised NEO Personality Inventory (NEO-PI-R) and NEO Five-Factor Inventory (NEO-FFI) professional manual. Psychological Assessment Resources.',
    ),
    'ORAIS': (
        'IPIP-ORAIS', 'IPIP Oregon Avocational Interest Scales', 'IPIP-ORAIS',
        'Personality',
        'https://ipip.ori.org/newORAISKey.htm',
        'Goldberg, L. R. (2010). Personality, demographics, and self-reported behavioral acts: The development of avocational interest markers. In C. R. Agnew, D. E. Carlston, W. G. Graziano, & J. R. Kelly (Eds.), Then a miracle occurs: Focusing on behavior in social psychological theory and research (pp. 205–234). Oxford University Press.',
    ),
    'Scheier1994': (
        'IPIP-Hope', 'IPIP Hope Scale', 'IPIP-Hope',
        'Well-being',
        'https://ipip.ori.org/newSingleConstructsKey.htm#Hope',
        'Scheier, M. F., Carver, C. S., & Bridges, M. W. (1994). Distinguishing optimism from neuroticism (and trait anxiety, self-mastery, and self-esteem): A reevaluation of the Life Orientation Test. Journal of Personality and Social Psychology, 67(6), 1063–1078. https://doi.org/10.1037/0022-3514.67.6.1063',
    ),
    'TCI': (
        'IPIP-TCI', 'IPIP Temperament and Character Inventory', 'IPIP-TCI',
        'Personality',
        'https://ipip.ori.org/newTCIKey.htm',
        'Cloninger, C. R., Przybeck, T. R., Svrakic, D. M., & Wetzel, R. D. (1994). The Temperament and Character Inventory (TCI): A guide to its development and use. Center for Psychobiology of Personality.',
    ),
}


def slugify(s: str) -> str:
    """Convert a label to a safe lowercase identifier."""
    s = s.lower()
    s = re.sub(r'[^a-z0-9]+', '_', s)
    s = s.strip('_')
    return s


def item_key_to_int(key) -> int:
    """Convert Excel key (1, -1, 0, '1', '-1') to int."""
    try:
        return int(float(key))
    except (TypeError, ValueError):
        return 1


def parse_alpha(alpha_val) -> str:
    """Return alpha as a string description, handling multi-value alphas."""
    if alpha_val is None:
        return ""
    s = str(alpha_val).strip()
    # May be "0.82,0.84" for dual samples
    parts = [p.strip() for p in s.split(',') if p.strip()]
    if len(parts) == 2:
        return f"Cronbach's alpha = {parts[0]} (community), {parts[1]} (clinical)"
    elif parts:
        return f"Cronbach's alpha = {parts[0]}"
    return ""


def make_osd(code: str, name: str, abbreviation: str, domain: str,
             url: str, citation: str, dimensions_data: list,
             description: str = "", text_to_code: dict = None) -> tuple:
    """
    Build a full OSD dict.

    dimensions_data: list of (dim_label, items_list)
      where items_list = [(key_int, text, alpha), ...]

    text_to_code: optional dict mapping item text → IPIP code (e.g. "H1131")
      Used to assign shared canonical text_key values across all IPIP OSD files.

    Returns (osd_dict, all_items, item_texts_list)
    """
    if text_to_code is None:
        text_to_code = {}

    all_items = []
    item_texts = []   # parallel list of English text strings
    dimensions = []
    scoring = {}

    item_counter = 1
    code_slug = slugify(code)

    for dim_label, items in dimensions_data:
        dim_id = slugify(dim_label)
        alpha_str = parse_alpha(items[0][2]) if items else ""

        dim_items = {}  # item_id → scoring key
        for key_int, text, alpha in items:
            # Scoring id is unique per OSD (drives dimension scoring)
            item_id = f"ipip_{code_slug}_{item_counter:03d}"
            # text_key is the shared IPIP canonical key (enables master translation)
            tkey = text_to_key(text, text_to_code)
            all_items.append({
                "id": item_id,
                "text_key": tkey,
                "type": "likert",
                "random_group": 1,
            })
            item_texts.append(text)
            dim_items[item_id] = key_int
            item_counter += 1

        # Sum dimension
        sum_id = dim_id + "_sum"
        dimensions.append({"id": sum_id, "name": dim_label + " (sum)"})
        scoring[sum_id] = {
            "description": alpha_str,
            "method": "sum",
            "items": dim_items,
        }

        # Mean dimension
        mean_id = dim_id + "_mean"
        dimensions.append({"id": mean_id, "name": dim_label + " (mean)"})
        scoring[mean_id] = {
            "description": alpha_str,
            "method": "mean_coded",
            "items": dim_items,
        }

    return {
        "osd_version": "1.0",
        "definition": {
            "scale_info": {
                "name": name,
                "code": code,
                "abbreviation": abbreviation,
                "description": description,
                "citation": citation,
                "license": "Public Domain",
                "version": "1.0",
                "url": url,
                "domain": domain,
            },
            "implementation": {
                "author": "Shane T. Mueller",
                "organization": "OpenScales Project",
                "date": "2026-05-02",
                "license": "CC BY 4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "notes": "Auto-generated from TedoneItemAssignmentTable30APR21.xlsx",
            },
            "likert_options": {
                "points": 5,
                "min": 1,
                "max": 5,
                "labels": IPIP_LIKERT_KEYS,
                "question_head": "ipip_question_head",
            },
            "parameters": {
                "shuffle_questions": {
                    "type": "boolean",
                    "default": 1,
                    "description": "Randomize item presentation order within the scale.",
                }
            },
            "dimensions": dimensions,
            "items": all_items,
            "scoring": scoring,
        },
        "translations": {},  # filled by write_osd
    }, all_items, item_texts


def write_osd(osd_path: Path, osd: dict, items: list, item_texts: list,
              master_en: dict, force: bool = False, dry_run: bool = False) -> bool:
    """Inject item translations and write OSD file. Also updates master_en in-place.

    Returns True if written.
    master_en: shared dict accumulating all English translations (text_key → text).
    """
    if osd_path.exists() and not force:
        print(f"  SKIP (exists): {osd_path.parent.name}")
        return False

    # Build English translations for this OSD using shared keys
    en = dict(IPIP_SHARED_EN)  # shared anchor + header keys
    for item, text in zip(items, item_texts):
        tkey = item["text_key"]
        en[tkey] = text
        master_en[tkey] = text  # accumulate into master

    osd["translations"] = {"en": en}

    if dry_run:
        print(f"  DRY-RUN: would write {osd_path} ({len(items)} items)")
        return False

    osd_path.parent.mkdir(parents=True, exist_ok=True)
    osd_path.write_text(json.dumps(osd, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


def process_instrument(inst: str, labels: dict, text_to_code: dict,
                       master_en: dict, force: bool, dry_run: bool) -> int:
    """Generate OSD file(s) for one instrument. Returns count of files written.

    text_to_code: item text → IPIP code lookup for canonical text_key assignment.
    master_en: accumulated English translation dict (updated in-place).
    """
    if inst not in INSTRUMENT_META:
        print(f"  WARNING: No metadata for {inst}, skipping")
        return 0

    code_prefix, name, abbreviation, domain, url, citation = INSTRUMENT_META[inst]
    total_items = sum(len(v) for v in labels.values())
    split = total_items > SPLIT_THRESHOLD

    written = 0

    # Short prefix for name (e.g. "IPIP CPI" instead of "IPIP California Psychological Inventory")
    name_prefix = INSTRUMENT_SHORT_PREFIX.get(inst, name)

    if split:
        # One OSD file per subscale
        for dim_label, items in labels.items():
            # Shorten label for code: strip parenthetical item counts
            clean_label = re.sub(r'\s*\(\d+\s*items?\)', '', dim_label).strip()

            # Look up official abbreviation for this subscale
            sub_abbrev = None
            for (inst_key, label_key), abbrev in SUBSCALE_ABBREVS.items():
                if inst_key == inst and label_key.lower() in clean_label.lower():
                    sub_abbrev = abbrev
                    break

            if sub_abbrev:
                osd_code = f"{code_prefix}-{sub_abbrev}"
                sub_abbreviation = f"{abbreviation.replace('IPIP-', '')}-{sub_abbrev}"
            else:
                osd_code = f"{code_prefix}-{re.sub(r'[^A-Za-z0-9]+', '-', clean_label).strip('-')}"
                sub_abbreviation = f"{abbreviation}-{slugify(clean_label)[:8]}"

            osd_path = SCALES_DIR / osd_code / f"{osd_code}.osd"
            dim_name = clean_label

            osd, item_objs, item_texts = make_osd(
                code=osd_code,
                name=f"{name_prefix}: {dim_name}",
                abbreviation=sub_abbreviation,
                domain=domain,
                url=url,
                citation=citation,
                dimensions_data=[(dim_name, items)],
                description=f"IPIP items measuring {dim_name.lower()}, from the {name}.",
                text_to_code=text_to_code,
            )
            if write_osd(osd_path, osd, item_objs, item_texts, master_en, force, dry_run):
                print(f"  Wrote {osd_code} ({len(items)} items)")
                written += 1

    else:
        # Single multi-dimension OSD
        osd_code = code_prefix
        osd_path = SCALES_DIR / osd_code / f"{osd_code}.osd"

        dims_data = []
        for dim_label, items in labels.items():
            clean_label = re.sub(r'\s*\(\d+\s*items?\)', '', dim_label).strip()
            dims_data.append((clean_label, items))

        osd, item_objs, item_texts = make_osd(
            code=osd_code,
            name=name,
            abbreviation=abbreviation,
            domain=domain,
            url=url,
            citation=citation,
            dimensions_data=dims_data,
            description=f"IPIP items measuring {name.lower().replace('ipip ', '')}.",
            text_to_code=text_to_code,
        )
        if write_osd(osd_path, osd, item_objs, item_texts, master_en, force, dry_run):
            print(f"  Wrote {osd_code} ({total_items} items, {len(labels)} dimensions)")
            written += 1

    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true', help='Overwrite existing OSD files')
    parser.add_argument('--instrument', help='Only process this instrument')
    parser.add_argument('--dry-run', action='store_true', help='Print without writing')
    args = parser.parse_args()

    if not EXCEL_PATH.exists():
        sys.exit(f"Excel file not found: {EXCEL_PATH}")

    # Load canonical IPIP item code lookup
    text_to_code = load_item_codes()
    print(f"Loaded {len(text_to_code)} IPIP item codes from {ITEM_CODES_PATH.name}")

    # Master English translation dict — accumulates across all OSD files
    master_en: dict = dict(IPIP_SHARED_EN)

    print(f"Reading {EXCEL_PATH} ...")
    wb = openpyxl.load_workbook(EXCEL_PATH)
    ws = wb.active

    # Group rows by instrument → label → [(key, text, alpha)]
    instruments = defaultdict(lambda: defaultdict(list))
    for row in ws.iter_rows(min_row=2, values_only=True):
        inst, alpha, key, text, label = row
        if inst and text:
            instruments[inst][label].append((item_key_to_int(key), str(text).strip(), alpha))

    total_written = 0
    skipped = 0

    for inst in sorted(instruments.keys()):
        if args.instrument and inst != args.instrument:
            continue
        if inst in SKIP_INSTRUMENTS:
            skipped += 1
            continue

        print(f"\n{inst} ({sum(len(v) for v in instruments[inst].values())} items, "
              f"{len(instruments[inst])} scales):")
        total_written += process_instrument(
            inst, instruments[inst], text_to_code, master_en, args.force, args.dry_run
        )

    if not args.dry_run and not args.instrument:
        # Write master English translation file
        MASTER_TRANS.write_text(
            json.dumps(master_en, indent=2, ensure_ascii=False) + "\n",
            encoding='utf-8'
        )
        print(f"\nWrote master English translations: {MASTER_TRANS}")
        print(f"  {len(master_en)} keys ({len(master_en) - len(IPIP_SHARED_EN)} item texts + {len(IPIP_SHARED_EN)} shared)")

    print(f"\nDone. Written: {total_written}  Skipped (existing): {skipped}")


if __name__ == "__main__":
    main()
