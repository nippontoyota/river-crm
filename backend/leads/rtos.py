import re
from difflib import SequenceMatcher


# Kerala MVD RTO / SRTO office codes, verified 2026-09-10.
# Source: https://mvd.kerala.gov.in/en/directory
KERALA_RTO_CHOICES = [
    ('KL-01', 'Trivandrum'),
    ('KL-02', 'Kollam'),
    ('KL-03', 'Pathanamthitta'),
    ('KL-04', 'Alappuzha'),
    ('KL-05', 'Kottayam'),
    ('KL-06', 'Idukki'),
    ('KL-07', 'Ernakulam'),
    ('KL-08', 'Thrissur'),
    ('KL-09', 'Palakkad'),
    ('KL-10', 'Malappuram'),
    ('KL-11', 'Kozhikkode'),
    ('KL-12', 'Wayanad'),
    ('KL-13', 'Kannur'),
    ('KL-14', 'Kasaragod'),
    ('KL-15', 'Nationalised Sector'),
    ('KL-16', 'Attingal'),
    ('KL-17', 'Muvattupuzha'),
    ('KL-18', 'Vadakkara'),
    ('KL-19', 'Parassala'),
    ('KL-20', 'Neyyattinkara'),
    ('KL-21', 'Nedumangadu'),
    ('KL-22', 'Kazhakuttom'),
    ('KL-23', 'Karunagappally'),
    ('KL-24', 'Kottarakkara'),
    ('KL-25', 'Punalur'),
    ('KL-26', 'Adoor'),
    ('KL-27', 'Thiruvalla'),
    ('KL-28', 'Mallappally'),
    ('KL-29', 'Kayamkulam'),
    ('KL-30', 'Chengannur'),
    ('KL-31', 'Mavelikkara'),
    ('KL-32', 'Cherthala'),
    ('KL-33', 'Changanassery'),
    ('KL-34', 'Kanjirappally'),
    ('KL-35', 'Pala'),
    ('KL-36', 'Vaikkom'),
    ('KL-37', 'Vandiperiyar'),
    ('KL-38', 'Thodupuzha'),
    ('KL-39', 'Tripunithura'),
    ('KL-40', 'Perumbavoor'),
    ('KL-41', 'Aluva'),
    ('KL-42', 'North Paroor'),
    ('KL-43', 'Mattancherry'),
    ('KL-44', 'Kothamangalam'),
    ('KL-45', 'Irinjalakkuda'),
    ('KL-46', 'Guruvayoor'),
    ('KL-47', 'Kodungallur'),
    ('KL-48', 'Vadakkancherry'),
    ('KL-49', 'Alathura'),
    ('KL-50', 'Mannarkkad'),
    ('KL-51', 'Ottappalam'),
    ('KL-52', 'Pattambi'),
    ('KL-53', 'Perinthalmanna'),
    ('KL-54', 'Ponnani'),
    ('KL-55', 'Tirur'),
    ('KL-56', 'Koyilandy'),
    ('KL-57', 'Koduvally'),
    ('KL-58', 'Thalassery'),
    ('KL-59', 'Thaliparamba'),
    ('KL-60', 'Kanhangad'),
    ('KL-61', 'Kunnathur'),
    ('KL-62', 'Ranni'),
    ('KL-63', 'Angamaly'),
    ('KL-64', 'Chalakkudy'),
    ('KL-65', 'Tirurangadi'),
    ('KL-66', 'Kuttanadu'),
    ('KL-67', 'Uzhavoor'),
    ('KL-68', 'Devikulam'),
    ('KL-69', 'Udumbanchola'),
    ('KL-70', 'Chittur'),
    ('KL-71', 'Nilambur'),
    ('KL-72', 'Mananthavady'),
    ('KL-73', 'Sulthanbathery'),
    ('KL-74', 'Kattakkada'),
    ('KL-75', 'Thriprayar'),
    ('KL-76', 'Nanmanda'),
    ('KL-77', 'Perambra'),
    ('KL-78', 'Iritty'),
    ('KL-79', 'Vellarikundu'),
    ('KL-80', 'Pathanapuram'),
    ('KL-81', 'Varkala'),
    ('KL-82', 'Chadayamangalam'),
    ('KL-83', 'Konni'),
    ('KL-84', 'Kondotty'),
    ('KL-85', 'Ramanattukara'),
    ('KL-86', 'Payyannur'),
]


def normalize_rto(value):
    """Resolve a code/name to one office; leave uncertain matches for review."""
    raw = str(value or '').strip().casefold()
    if not raw:
        return ''
    if re.fullmatch(r'[0-9]{1,2}', raw):
        raw = f'kl{raw}'
    code_pattern = r'\bk[\W_]*l[\W_]*([0-9]{1,3})(?![0-9])'
    codes = {f'KL-{int(number):02d}' for number in re.findall(code_pattern, raw)}
    if len(codes) > 1 or codes - dict(KERALA_RTO_CHOICES).keys():
        return None
    code = next(iter(codes), None)
    name = re.sub(code_pattern, '', raw)
    name = re.sub(r'\b(?:sub[\s-]*)?regional[\s-]+transport[\s-]+office\b|\b(?:s[\s-]*rto|rto|office|code|kerala)\b', '', name)
    name = ''.join(character for character in name if character.isalnum())
    if not name:
        return code
    names = {''.join(c for c in label.casefold() if c.isalnum()): key for key, label in KERALA_RTO_CHOICES}
    names['thiruvananthapuram'] = 'KL-01'
    match = names.get(name)
    if not match:
        # Short/ambiguous fragments must never guess a customer's RTO.
        if len(name) < 5 or any(c.isdigit() for c in name):
            return None
        scores = {}
        for label, key in names.items():
            scores[key] = max(scores.get(key, 0), SequenceMatcher(None, name, label).ratio())
        ranked = sorted(scores, key=scores.get, reverse=True)
        if scores[ranked[0]] < 0.84 or scores[ranked[0]] - scores[ranked[1]] < 0.08:
            return None
        match = ranked[0]
    return match if code is None or code == match else None
