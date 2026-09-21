import re
from difflib import SequenceMatcher


# Office names match the RTO NAME column in RTO List.csv.
# Keep stored codes unchanged for existing leads and report filters.
KERALA_RTO_CHOICES = [
    ('KL-01', 'Thiruvananthapuram'),
    ('KL-02', 'Kollam'),
    ('KL-03', 'Pathanamthitta'),
    ('KL-04', 'Alappuzha'),
    ('KL-05', 'Kottayam'),
    ('KL-06', 'Idukki'),
    ('KL-07', 'Ernakulam'),
    ('KL-08', 'Thrissur'),
    ('KL-09', 'Palakkad'),
    ('KL-10', 'Malappuram'),
    ('KL-11', 'Kozhikode'),
    ('KL-12', 'Wayanad'),
    ('KL-13', 'Kannur'),
    ('KL-14', 'Kasargod'),
    ('KL-15', 'KSRTC'),
    ('KL-16', 'Attingal'),
    ('KL-17', 'Muvattupuzha'),
    ('KL-18', 'Vadakara'),
    ('KL-19', 'Parassala'),
    ('KL-20', 'Neyyattinkara'),
    ('KL-21', 'Nedumangad'),
    ('KL-22', 'Kazhakoottam'),
    ('KL-23', 'Karunagappalli'),
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
    ('KL-36', 'Vaikom'),
    ('KL-37', 'Vandiperiyar'),
    ('KL-38', 'Thodupuzha'),
    ('KL-39', 'Thripunithura'),
    ('KL-40', 'Perumbavoor'),
    ('KL-41', 'Aluva'),
    ('KL-42', 'North Paravur'),
    ('KL-43', 'Mattancherry'),
    ('KL-44', 'Kothamangalam'),
    ('KL-45', 'Irinjalakuda'),
    ('KL-46', 'Guruvayur'),
    ('KL-47', 'Kodungalloor'),
    ('KL-48', 'Wadakkanchery'),
    ('KL-49', 'Alathur'),
    ('KL-50', 'Mannarkkad'),
    ('KL-51', 'Ottappalam'),
    ('KL-52', 'Pattambi'),
    ('KL-53', 'Perinthalmanna'),
    ('KL-54', 'Ponnani'),
    ('KL-55', 'Tirur'),
    ('KL-56', 'Koyilandy'),
    ('KL-57', 'Koduvally'),
    ('KL-58', 'Thalassery'),
    ('KL-59', 'Taliparamba'),
    ('KL-60', 'Kanhangad'),
    ('KL-61', 'Kunnathur'),
    ('KL-62', 'Ranni'),
    ('KL-63', 'Angamaly'),
    ('KL-64', 'Chalakkudy'),
    ('KL-65', 'Tirurangadi'),
    ('KL-66', 'Kuttanad'),
    ('KL-67', 'Uzhavoor'),
    ('KL-68', 'Devikulam'),
    ('KL-69', 'Udumbanchola'),
    ('KL-70', 'Chittur'),
    ('KL-71', 'Nilambur'),
    ('KL-72', 'Mananthavady'),
    ('KL-73', 'Sulthan Bathery'),
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
    # Preserve previous names that no longer pass conservative spelling matching.
    names.update({'trivandrum': 'KL-01', 'nationalisedsector': 'KL-15', 'kazhakuttom': 'KL-22', 'northparoor': 'KL-42'})
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
