"""Conservative US eligibility from employer locations, not website locale."""
import re

US_PLACES = r'san francisco|bay area|san jose|santa clara|sunnyvale|mountain view|cupertino|palo alto|menlo park|redwood city|foster city|los angeles|santa monica|culver city|irvine|seattle|bellevue|redmond|minnesota|minneapolis|st\.? paul|boston|worcester|waltham|chicago|indianapolis|san diego|thousand oaks|new york|nyc|brooklyn|raritan|titusville|spring house|horsham|new brunswick|louisville|san bruno'
FOREIGN = r'india|hyderabad|bengaluru|bangalore|canada|burnaby|toronto|montreal|united kingdom|uk|england|london|great abington|germany|ludwigshafen|munich|france|boulogne-billancourt|ireland|westport|poland|portugal|lisbon|taiwan|taipei|china|beijing|singapore|japan|tokyo|slovakia|bratislava|israel|yokneam|tel aviv|austria|italy|campoverde|spain|madrid|barcelona|australia|argentina|mexico|switzerland|belgium|beerse|netherlands|south korea|brazil|czechia|denmark|sweden|finland|norway'


def country_scope(item):
    countries = {c.upper() for c in item.get('countries', []) if c}
    if countries:
        return 'us' if countries & {'US', 'USA', 'UNITED STATES', 'UNITED STATES OF AMERICA'} else 'non_us'
    text = item.get('location', '')
    if re.search(r'not (?:shown|specified|stated|visible)|verify|snippet|unknown|appears|did not|not clearly', text, re.I):
        return 'unknown'
    if re.search(r'\b(united states(?: of america)?|usa|us)\b', text, re.I) or re.search(r'\b(' + US_PLACES + r')\b', text, re.I):
        return 'us'
    if re.search(r'\b(' + FOREIGN + r')\b', text, re.I) or re.search(r',\s*(de|gb|fr|ie|it|pl|pt|es|ch|au|in|jp|cn|ca)\s*$', text):
        return 'non_us'
    # State abbreviations need a city/comma context; bare CA may mean Canada.
    if re.search(r',\s*(?:CA|WA|MN|MA|IL|IN|NJ|PA|CT|NC|OH|CO|GA|TX|FL|VA|MD|AZ|OR)\b', text):
        return 'us'
    return 'unknown'
