"""
Company career URL discovery module.
Attempts to find career APIs for companies using common patterns.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
import pandas as pd

logger = logging.getLogger(__name__)

# Known company to career URL mappings
KNOWN_COMPANIES = {
    # Format: "company_name_lowercase": ("api_url", "type")
    "23andme": ("https://boards.greenhouse.io/23andme", "greenhouse"),
    "3m": ("https://3m.wd1.myworkdayjobs.com/wday/cxs/3m/3M/jobs", "workday"),
    "abbott": ("https://abbott.wd5.myworkdayjobs.com/wday/cxs/abbott/abbottcareers/jobs", "workday"),
    "abbvie": ("https://abbvie.wd5.myworkdayjobs.com/wday/cxs/abbvie/abbvie/jobs", "workday"),
    "accenture": ("https://accenture.wd3.myworkdayjobs.com/wday/cxs/accenture/AccentureCareers/jobs", "workday"),
    "activision": ("https://boards.greenhouse.io/activisionblizzard", "greenhouse"),
    "activision blizzard": ("https://boards.greenhouse.io/activisionblizzard", "greenhouse"),
    "adobe": ("https://adobe.wd5.myworkdayjobs.com/wday/cxs/adobe/external_experienced/jobs", "workday"),
    "adp": ("https://adp.wd5.myworkdayjobs.com/wday/cxs/adp/External_Career_Site/jobs", "workday"),
    "aetna": ("https://aetna.wd5.myworkdayjobs.com/wday/cxs/aetna/aetnacareers/jobs", "workday"),
    "affirm": ("https://boards.greenhouse.io/affirm", "greenhouse"),
    "agilent": ("https://agilent.wd1.myworkdayjobs.com/wday/cxs/agilent/External/jobs", "workday"),
    "airbnb": ("https://boards.greenhouse.io/airbnb", "greenhouse"),
    "akamai": ("https://akamai.wd1.myworkdayjobs.com/wday/cxs/akamai/akamaicareers/jobs", "workday"),
    "albertsons": ("https://albertsons.wd5.myworkdayjobs.com/wday/cxs/albertsons/External/jobs", "workday"),
    "allstate": ("https://allstate.wd5.myworkdayjobs.com/wday/cxs/allstate/allstate_careers/jobs", "workday"),
    "alphabet": ("https://careers.google.com/api/v3/search/", "google"),
    "amazon": ("https://www.amazon.jobs/en/search.json", "amazon"),
    "amd": ("https://amd.wd1.myworkdayjobs.com/wday/cxs/amd/AMD/jobs", "workday"),
    "american express": ("https://aexp.wd5.myworkdayjobs.com/wday/cxs/aexp/American_Express_Careers/jobs", "workday"),
    "amgen": ("https://amgen.wd1.myworkdayjobs.com/wday/cxs/amgen/Careers/jobs", "workday"),
    "anthem": ("https://anthemcareers.wd5.myworkdayjobs.com/wday/cxs/anthemcareers/external/jobs", "workday"),
    "apple": ("https://jobs.apple.com/api/role/search", "apple"),
    "applied materials": ("https://amat.wd1.myworkdayjobs.com/wday/cxs/amat/External/jobs", "workday"),
    "arista": ("https://boards.greenhouse.io/arista", "greenhouse"),
    "asana": ("https://boards.greenhouse.io/asana", "greenhouse"),
    "astrazeneca": ("https://astrazeneca.wd3.myworkdayjobs.com/wday/cxs/astrazeneca/Careers/jobs", "workday"),
    "atlassian": ("https://boards.greenhouse.io/atlassian", "greenhouse"),
    "autodesk": ("https://autodesk.wd1.myworkdayjobs.com/wday/cxs/autodesk/Ext/jobs", "workday"),
    "automattic": ("https://boards.greenhouse.io/automattic", "greenhouse"),
    "baidu": ("https://talent.baidu.com/external/baidu/index.html", "custom"),
    "bain": ("https://boards.greenhouse.io/baboratories", "greenhouse"),
    "bank of america": ("https://ghr.wd1.myworkdayjobs.com/wday/cxs/ghr/BAC_Careers/jobs", "workday"),
    "bayer": ("https://bayer.wd3.myworkdayjobs.com/wday/cxs/bayer/BayerCareerUSA/jobs", "workday"),
    "bd": ("https://bd.wd1.myworkdayjobs.com/wday/cxs/bd/BDX_Careers/jobs", "workday"),
    "better.com": ("https://boards.greenhouse.io/better", "greenhouse"),
    "blackrock": ("https://blackrock.wd1.myworkdayjobs.com/wday/cxs/blackrock/BlackRock/jobs", "workday"),
    "bloomberg": ("https://bloomberg.wd1.myworkdayjobs.com/wday/cxs/bloomberg/careers/jobs", "workday"),
    "blue origin": ("https://blueorigin.wd5.myworkdayjobs.com/wday/cxs/blueorigin/BlueOrigin/jobs", "workday"),
    "boeing": ("https://boeing.wd1.myworkdayjobs.com/wday/cxs/boeing/EXTERNAL_CAREERS/jobs", "workday"),
    "booking": ("https://booking.wd3.myworkdayjobs.com/wday/cxs/booking/BookingCareers/jobs", "workday"),
    "booz allen": ("https://bah.wd1.myworkdayjobs.com/wday/cxs/bah/BAH_Jobs/jobs", "workday"),
    "boston dynamics": ("https://bostondynamics.wd1.myworkdayjobs.com/wday/cxs/bostondynamics/Boston_Dynamics/jobs", "workday"),
    "boston scientific": ("https://bostonscientific.wd1.myworkdayjobs.com/wday/cxs/bostonscientific/BSCCareers/jobs", "workday"),
    "box": ("https://boards.greenhouse.io/box", "greenhouse"),
    "braze": ("https://boards.greenhouse.io/braze", "greenhouse"),
    "broadcom": ("https://broadcom.wd1.myworkdayjobs.com/wday/cxs/broadcom/External_Careers/jobs", "workday"),
    "c3.ai": ("https://boards.greenhouse.io/c3iot", "greenhouse"),
    "cadence": ("https://cadence.wd1.myworkdayjobs.com/wday/cxs/cadence/External_Careers/jobs", "workday"),
    "capital one": ("https://capitalone.wd1.myworkdayjobs.com/wday/cxs/capitalone/Capital_One/jobs", "workday"),
    "cardinal health": ("https://cardinalhealth.wd1.myworkdayjobs.com/wday/cxs/cardinalhealth/cardinal_health/jobs", "workday"),
    "cargill": ("https://cargill.wd1.myworkdayjobs.com/wday/cxs/cargill/CargillCareers/jobs", "workday"),
    "centene": ("https://centene.wd1.myworkdayjobs.com/wday/cxs/centene/Centene/jobs", "workday"),
    "charles schwab": ("https://schwab.wd1.myworkdayjobs.com/wday/cxs/schwab/SchwabCareers/jobs", "workday"),
    "charter": ("https://charter.wd1.myworkdayjobs.com/wday/cxs/charter/External/jobs", "workday"),
    "chewy": ("https://chewyinc.wd1.myworkdayjobs.com/wday/cxs/chewyinc/Chewy/jobs", "workday"),
    "chime": ("https://boards.greenhouse.io/chime", "greenhouse"),
    "cisco": ("https://cisco.wd1.myworkdayjobs.com/wday/cxs/cisco/External_Careers/jobs", "workday"),
    "citi": ("https://citi.wd5.myworkdayjobs.com/wday/cxs/citi/2/jobs", "workday"),
    "citigroup": ("https://citi.wd5.myworkdayjobs.com/wday/cxs/citi/2/jobs", "workday"),
    "cloudflare": ("https://boards.greenhouse.io/cloudflare", "greenhouse"),
    "coca-cola": ("https://coke.wd1.myworkdayjobs.com/wday/cxs/coke/CocaColaCareers/jobs", "workday"),
    "cognizant": ("https://cognizant.wd1.myworkdayjobs.com/wday/cxs/cognizant/Cognizant_Careers/jobs", "workday"),
    "cohere": ("https://jobs.lever.co/cohere", "lever"),
    "coinbase": ("https://boards.greenhouse.io/coinbase", "greenhouse"),
    "colgate": ("https://colgate.wd1.myworkdayjobs.com/wday/cxs/colgate/ColgateKnowledgePlatform/jobs", "workday"),
    "comcast": ("https://comcast.wd5.myworkdayjobs.com/wday/cxs/comcast/Comcast_Careers/jobs", "workday"),
    "corning": ("https://corning.wd5.myworkdayjobs.com/wday/cxs/corning/careers/jobs", "workday"),
    "costco": ("https://costco.wd5.myworkdayjobs.com/wday/cxs/costco/costco_careers/jobs", "workday"),
    "coursera": ("https://boards.greenhouse.io/coursera", "greenhouse"),
    "cruise": ("https://boards.greenhouse.io/cruise", "greenhouse"),
    "cvs": ("https://cvshealth.wd1.myworkdayjobs.com/wday/cxs/cvshealth/CVS_Health_Careers/jobs", "workday"),
    "danaher": ("https://danaher.wd1.myworkdayjobs.com/wday/cxs/danaher/DanaherCareers/jobs", "workday"),
    "databricks": ("https://boards.greenhouse.io/databricks", "greenhouse"),
    "datadog": ("https://boards.greenhouse.io/datadog", "greenhouse"),
    "dell": ("https://dell.wd1.myworkdayjobs.com/wday/cxs/dell/External/jobs", "workday"),
    "deloitte": ("https://deloitte.wd1.myworkdayjobs.com/wday/cxs/deloitte/deloittecareers/jobs", "workday"),
    "delta": ("https://delta.wd1.myworkdayjobs.com/wday/cxs/delta/DL_External/jobs", "workday"),
    "discord": ("https://boards.greenhouse.io/discord", "greenhouse"),
    "disney": ("https://disney.wd5.myworkdayjobs.com/wday/cxs/disney/disneycareer/jobs", "workday"),
    "docusign": ("https://docusign.wd1.myworkdayjobs.com/wday/cxs/docusign/DocuSign/jobs", "workday"),
    "doordash": ("https://boards.greenhouse.io/doordash", "greenhouse"),
    "dropbox": ("https://boards.greenhouse.io/dropbox", "greenhouse"),
    "duolingo": ("https://boards.greenhouse.io/duolingo", "greenhouse"),
    "ea": ("https://ea.gr8people.com/jobs", "custom"),
    "ebay": ("https://ebay.wd5.myworkdayjobs.com/wday/cxs/ebay/apply/jobs", "workday"),
    "edwards lifesciences": ("https://edwards.wd1.myworkdayjobs.com/wday/cxs/edwards/Edwards_Careers/jobs", "workday"),
    "eli lilly": ("https://lilly.wd5.myworkdayjobs.com/wday/cxs/lilly/LillyExternalHQ/jobs", "workday"),
    "epic": ("https://boards.greenhouse.io/epicgames", "greenhouse"),
    "epic games": ("https://boards.greenhouse.io/epicgames", "greenhouse"),
    "equifax": ("https://equifax.wd5.myworkdayjobs.com/wday/cxs/equifax/External/jobs", "workday"),
    "etsy": ("https://boards.greenhouse.io/etsy", "greenhouse"),
    "expedia": ("https://expedia.wd5.myworkdayjobs.com/wday/cxs/expedia/search/jobs", "workday"),
    "exxon": ("https://exxonmobil.wd5.myworkdayjobs.com/wday/cxs/exxonmobil/search/jobs", "workday"),
    "facebook": ("https://www.metacareers.com/jobs", "meta"),
    "fannie mae": ("https://fanniemae.wd1.myworkdayjobs.com/wday/cxs/fanniemae/FannieMaeExternalCareers/jobs", "workday"),
    "fedex": ("https://fedex.wd1.myworkdayjobs.com/wday/cxs/fedex/FedEx_Careers/jobs", "workday"),
    "fidelity": ("https://fmr.wd1.myworkdayjobs.com/wday/cxs/fmr/FidelityCareers/jobs", "workday"),
    "figma": ("https://boards.greenhouse.io/figma", "greenhouse"),
    "flatiron health": ("https://boards.greenhouse.io/flatironhealth", "greenhouse"),
    "ford": ("https://ford.wd1.myworkdayjobs.com/wday/cxs/ford/FordMotorCompanyCareers/jobs", "workday"),
    "ge": ("https://ge.wd5.myworkdayjobs.com/wday/cxs/ge/GE_Careers/jobs", "workday"),
    "ge healthcare": ("https://gehealthcare.wd1.myworkdayjobs.com/wday/cxs/gehealthcare/GEHealthcareCareers/jobs", "workday"),
    "genentech": ("https://gene.wd5.myworkdayjobs.com/wday/cxs/gene/genentech/jobs", "workday"),
    "general mills": ("https://generalmills.wd5.myworkdayjobs.com/wday/cxs/generalmills/GMJOBS/jobs", "workday"),
    "general motors": ("https://generalmotors.wd5.myworkdayjobs.com/wday/cxs/generalmotors/Careers_GM/jobs", "workday"),
    "gilead": ("https://gilead.wd1.myworkdayjobs.com/wday/cxs/gilead/gaborone/jobs", "workday"),
    "github": ("https://boards.greenhouse.io/github", "greenhouse"),
    "gitlab": ("https://boards.greenhouse.io/gitlab", "greenhouse"),
    "gm": ("https://generalmotors.wd5.myworkdayjobs.com/wday/cxs/generalmotors/Careers_GM/jobs", "workday"),
    "gojek": ("https://boards.greenhouse.io/gojek", "greenhouse"),
    "goldman sachs": ("https://hdpc.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions", "oracle"),
    "google": ("https://careers.google.com/api/v3/search/", "google"),
    "grammarly": ("https://boards.greenhouse.io/grammarly", "greenhouse"),
    "guidewire": ("https://guidewire.wd1.myworkdayjobs.com/wday/cxs/guidewire/GuidewireCareers/jobs", "workday"),
    "hbo": ("https://warnerbros.wd5.myworkdayjobs.com/wday/cxs/warnerbros/global/jobs", "workday"),
    "hewlett packard enterprise": ("https://hpe.wd5.myworkdayjobs.com/wday/cxs/hpe/Jobsathpe/jobs", "workday"),
    "honeywell": ("https://honeywell.wd5.myworkdayjobs.com/wday/cxs/honeywell/Honeywell_Careers/jobs", "workday"),
    "hp": ("https://hp.wd5.myworkdayjobs.com/wday/cxs/hp/ExternalCareerSite/jobs", "workday"),
    "hpe": ("https://hpe.wd5.myworkdayjobs.com/wday/cxs/hpe/Jobsathpe/jobs", "workday"),
    "hubspot": ("https://boards.greenhouse.io/hubspot", "greenhouse"),
    "hugging face": ("https://apply.workable.com/api/v1/widget/accounts/huggingface/jobs", "workable"),
    "humana": ("https://humana.wd5.myworkdayjobs.com/wday/cxs/humana/Humana/jobs", "workday"),
    "ibm": ("https://ibm.wd1.myworkdayjobs.com/wday/cxs/ibm/IBM_Careers/jobs", "workday"),
    "illumina": ("https://illumina.wd1.myworkdayjobs.com/wday/cxs/illumina/illumina-careers/jobs", "workday"),
    "indeed": ("https://indeed.wd1.myworkdayjobs.com/wday/cxs/indeed/Indeed_Jobs/jobs", "workday"),
    "instacart": ("https://boards.greenhouse.io/instacart", "greenhouse"),
    "intel": ("https://intel.wd1.myworkdayjobs.com/wday/cxs/intel/External/jobs", "workday"),
    "intuit": ("https://intuit.wd1.myworkdayjobs.com/wday/cxs/intuit/Intuit/jobs", "workday"),
    "johnson & johnson": ("https://jnj.wd1.myworkdayjobs.com/wday/cxs/jnj/global_careers/jobs", "workday"),
    "jpmorgan": ("https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions", "oracle"),
    "juniper": ("https://juniper.wd1.myworkdayjobs.com/wday/cxs/juniper/junipercareers/jobs", "workday"),
    "kla": ("https://kla.wd1.myworkdayjobs.com/wday/cxs/kla/KLA_Careers/jobs", "workday"),
    "klaviyo": ("https://boards.greenhouse.io/klaviyo", "greenhouse"),
    "kraft heinz": ("https://kraftheinz.wd5.myworkdayjobs.com/wday/cxs/kraftheinz/khcjobs/jobs", "workday"),
    "lam research": ("https://lamresearch.wd1.myworkdayjobs.com/wday/cxs/lamresearch/Careers/jobs", "workday"),
    "lenovo": ("https://lenovo.wd1.myworkdayjobs.com/wday/cxs/lenovo/Lenovo_Careers/jobs", "workday"),
    "linkedin": ("https://linkedin.wd1.myworkdayjobs.com/wday/cxs/linkedin/jobs/jobs", "workday"),
    "lockheed martin": ("https://lockheedmartin.wd1.myworkdayjobs.com/wday/cxs/lockheedmartin/External/jobs", "workday"),
    "lowe's": ("https://lowes.wd5.myworkdayjobs.com/wday/cxs/lowes/lowescareers/jobs", "workday"),
    "lyft": ("https://boards.greenhouse.io/lyft", "greenhouse"),
    "mailchimp": ("https://boards.greenhouse.io/mailchimp", "greenhouse"),
    "marqeta": ("https://boards.greenhouse.io/marqeta", "greenhouse"),
    "marvell": ("https://marvell.wd1.myworkdayjobs.com/wday/cxs/marvell/MarvellCareers/jobs", "workday"),
    "mastercard": ("https://mastercard.wd1.myworkdayjobs.com/wday/cxs/mastercard/CorporateCareers/jobs", "workday"),
    "mckinsey": ("https://boards.greenhouse.io/mckinsey", "greenhouse"),
    "medtronic": ("https://medtronic.wd1.myworkdayjobs.com/wday/cxs/medtronic/MedtronicCareers/jobs", "workday"),
    "merck": ("https://msd.wd5.myworkdayjobs.com/wday/cxs/msd/SearchJobs/jobs", "workday"),
    "meta": ("https://www.metacareers.com/jobs", "meta"),
    "micron": ("https://micron.wd1.myworkdayjobs.com/wday/cxs/micron/External/jobs", "workday"),
    "microsoft": ("https://gcsservices.careers.microsoft.com/search/api/v1/search", "microsoft"),
    "moderna": ("https://boards.greenhouse.io/modernatx", "greenhouse"),
    "mongodb": ("https://boards.greenhouse.io/mongodb", "greenhouse"),
    "morgan stanley": ("https://morganstanley.wd5.myworkdayjobs.com/wday/cxs/morganstanley/mscareers/jobs", "workday"),
    "netflix": ("https://jobs.netflix.com/api/search", "netflix"),
    "northrop grumman": ("https://northropgrumman.wd1.myworkdayjobs.com/wday/cxs/northropgrumman/Northrop_Grumman_External_Site/jobs", "workday"),
    "notion": ("https://boards.greenhouse.io/notion", "greenhouse"),
    "nuro": ("https://boards.greenhouse.io/nuro", "greenhouse"),
    "nutanix": ("https://nutanix.wd1.myworkdayjobs.com/wday/cxs/nutanix/Nutanix_Careers/jobs", "workday"),
    "nvidia": ("https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs", "workday"),
    "okta": ("https://boards.greenhouse.io/okta", "greenhouse"),
    "openai": ("https://boards.greenhouse.io/openai", "greenhouse"),
    "oracle": ("https://oracle.wd1.myworkdayjobs.com/wday/cxs/oracle/Oracle_Careers/jobs", "workday"),
    "pagerduty": ("https://boards.greenhouse.io/pagerduty", "greenhouse"),
    "palantir": ("https://jobs.lever.co/palantir", "lever"),
    "palo alto networks": ("https://paloaltonetworks.wd1.myworkdayjobs.com/wday/cxs/paloaltonetworks/External/jobs", "workday"),
    "paypal": ("https://paypal.wd1.myworkdayjobs.com/wday/cxs/paypal/jobs/jobs", "workday"),
    "peloton": ("https://boards.greenhouse.io/peloton", "greenhouse"),
    "pepsico": ("https://pepsico.wd1.myworkdayjobs.com/wday/cxs/pepsico/pepsico_jobs/jobs", "workday"),
    "pfizer": ("https://pfizer.wd1.myworkdayjobs.com/wday/cxs/pfizer/PfizerCareers/jobs", "workday"),
    "pinterest": ("https://boards.greenhouse.io/pinterest", "greenhouse"),
    "plaid": ("https://boards.greenhouse.io/plaid", "greenhouse"),
    "procter & gamble": ("https://pg.wd1.myworkdayjobs.com/wday/cxs/pg/PGCareers/jobs", "workday"),
    "prudential": ("https://prudential.wd5.myworkdayjobs.com/wday/cxs/prudential/External/jobs", "workday"),
    "qualcomm": ("https://qualcomm.wd5.myworkdayjobs.com/wday/cxs/qualcomm/External/jobs", "workday"),
    "qualtrics": ("https://boards.greenhouse.io/qualtrics", "greenhouse"),
    "ramp": ("https://boards.greenhouse.io/ramp", "greenhouse"),
    "raytheon": ("https://rtx.wd1.myworkdayjobs.com/wday/cxs/rtx/RTX/jobs", "workday"),
    "reddit": ("https://boards.greenhouse.io/reddit", "greenhouse"),
    "regeneron": ("https://regeneron.wd1.myworkdayjobs.com/wday/cxs/regeneron/RegeneronCareers/jobs", "workday"),
    "replit": ("https://boards.greenhouse.io/replit", "greenhouse"),
    "rippling": ("https://boards.greenhouse.io/rippling", "greenhouse"),
    "robinhood": ("https://boards.greenhouse.io/robinhood", "greenhouse"),
    "roblox": ("https://boards.greenhouse.io/roblox", "greenhouse"),
    "roku": ("https://boards.greenhouse.io/roku", "greenhouse"),
    "salesforce": ("https://salesforce.wd12.myworkdayjobs.com/wday/cxs/salesforce/External_Career_Site/jobs", "workday"),
    "samsung": ("https://sec.wd3.myworkdayjobs.com/wday/cxs/sec/Samsung_Careers/jobs", "workday"),
    "samsara": ("https://boards.greenhouse.io/samsara", "greenhouse"),
    "sap": ("https://sap.wd1.myworkdayjobs.com/wday/cxs/sap/SAPCareers/jobs", "workday"),
    "scale ai": ("https://boards.greenhouse.io/scaleai", "greenhouse"),
    "schwab": ("https://schwab.wd1.myworkdayjobs.com/wday/cxs/schwab/SchwabCareers/jobs", "workday"),
    "seagate": ("https://seagate.wd1.myworkdayjobs.com/wday/cxs/seagate/SeagateCareers/jobs", "workday"),
    "servicenow": ("https://servicenow.wd1.myworkdayjobs.com/wday/cxs/servicenow/servicenow_careers/jobs", "workday"),
    "shopify": ("https://boards.greenhouse.io/shopify", "greenhouse"),
    "siemens": ("https://jobs.siemens.com/api/apply/v2/jobs", "custom"),
    "slack": ("https://salesforce.wd12.myworkdayjobs.com/wday/cxs/salesforce/Slack/jobs", "workday"),
    "snap": ("https://wd1.myworkdaysite.com/recruiting/snap/snap/jobs", "workday"),
    "snowflake": ("https://boards.greenhouse.io/snowflake", "greenhouse"),
    "sofi": ("https://sofi.wd5.myworkdayjobs.com/wday/cxs/sofi/SoFi/jobs", "workday"),
    "sony": ("https://sonyglobal.wd1.myworkdayjobs.com/wday/cxs/sonyglobal/SonyGlobalCareers/jobs", "workday"),
    "spacex": ("https://boards.greenhouse.io/spacex", "greenhouse"),
    "splunk": ("https://splunk.wd1.myworkdayjobs.com/wday/cxs/splunk/Splunk/jobs", "workday"),
    "spotify": ("https://www.lifeatspotify.com/jobs", "custom"),
    "square": ("https://boards.greenhouse.io/squareup", "greenhouse"),
    "stability ai": ("https://jobs.lever.co/stability.ai", "lever"),
    "starbucks": ("https://starbucks.wd1.myworkdayjobs.com/wday/cxs/starbucks/StarbucksCareers/jobs", "workday"),
    "state farm": ("https://statefarm.wd5.myworkdayjobs.com/wday/cxs/statefarm/StateFarmCareers/jobs", "workday"),
    "stripe": ("https://boards.greenhouse.io/stripe", "greenhouse"),
    "synopsys": ("https://synopsys.wd1.myworkdayjobs.com/wday/cxs/synopsys/SynopsysCareers/jobs", "workday"),
    "target": ("https://target.wd5.myworkdayjobs.com/wday/cxs/target/targetcareers/jobs", "workday"),
    "tempus": ("https://boards.greenhouse.io/tempus", "greenhouse"),
    "tesla": ("https://www.tesla.com/cua-api/apps/careers/state", "tesla"),
    "thermo fisher": ("https://thermofisher.wd1.myworkdayjobs.com/wday/cxs/thermofisher/ExternalCareers/jobs", "workday"),
    "tiktok": ("https://careers.tiktok.com/api/v1/search/job/posts", "tiktok"),
    "toast": ("https://boards.greenhouse.io/toast", "greenhouse"),
    "truveta": ("https://boards.greenhouse.io/truveta", "greenhouse"),
    "twilio": ("https://boards.greenhouse.io/twilio", "greenhouse"),
    "two sigma": ("https://boards.greenhouse.io/twosigma", "greenhouse"),
    "uber": ("https://boards.greenhouse.io/uber", "greenhouse"),
    "united airlines": ("https://united.wd1.myworkdayjobs.com/wday/cxs/united/External/jobs", "workday"),
    "unitedhealth": ("https://uhg.wd1.myworkdayjobs.com/wday/cxs/uhg/UnitedHealthGroup/jobs", "workday"),
    "unity": ("https://boards.greenhouse.io/unity3d", "greenhouse"),
    "ups": ("https://ups.wd1.myworkdayjobs.com/wday/cxs/ups/UPSCareers/jobs", "workday"),
    "usaa": ("https://usaa.wd1.myworkdayjobs.com/wday/cxs/usaa/USAA_External_Careers/jobs", "workday"),
    "veeva": ("https://veeva.wd1.myworkdayjobs.com/wday/cxs/veeva/Veeva_Careers/jobs", "workday"),
    "verily": ("https://boards.greenhouse.io/verily", "greenhouse"),
    "verizon": ("https://verizon.wd5.myworkdayjobs.com/wday/cxs/verizon/verizon_careers/jobs", "workday"),
    "visa": ("https://visa.wd5.myworkdayjobs.com/wday/cxs/visa/VisaCareers/jobs", "workday"),
    "vmware": ("https://vmware.wd1.myworkdayjobs.com/wday/cxs/vmware/VMwareCareers/jobs", "workday"),
    "walmart": ("https://walmart.wd5.myworkdayjobs.com/wday/cxs/walmart/WalmartExternal/jobs", "workday"),
    "warner bros": ("https://warnerbros.wd5.myworkdayjobs.com/wday/cxs/warnerbros/global/jobs", "workday"),
    "wayfair": ("https://boards.greenhouse.io/wayfair", "greenhouse"),
    "waymo": ("https://boards.greenhouse.io/waymo", "greenhouse"),
    "wealthfront": ("https://boards.greenhouse.io/wealthfront", "greenhouse"),
    "wells fargo": ("https://wellsfargo.wd1.myworkdayjobs.com/wday/cxs/wellsfargo/WF_External_Careers/jobs", "workday"),
    "western digital": ("https://wdc.wd1.myworkdayjobs.com/wday/cxs/wdc/WD_CAREERS/jobs", "workday"),
    "workday": ("https://workday.wd5.myworkdayjobs.com/wday/cxs/workday/Workday/jobs", "workday"),
    "zillow": ("https://zillow.wd5.myworkdayjobs.com/wday/cxs/zillow/Zillow_Group_Careers/jobs", "workday"),
    "zoom": ("https://zoom.wd5.myworkdayjobs.com/wday/cxs/zoom/Zoom/jobs", "workday"),
    "zoox": ("https://boards.greenhouse.io/zoox", "greenhouse"),
    "zscaler": ("https://zscaler.wd1.myworkdayjobs.com/wday/cxs/zscaler/ZscalerCareers/jobs", "workday"),
}


def normalize_company_name(name: str) -> str:
    """Normalize company name for matching."""
    # Remove common suffixes and clean up
    name = name.lower().strip()
    name = re.sub(r'\s*(inc\.?|corp\.?|corporation|company|co\.?|llc|ltd\.?|plc|group|holdings?)\.?\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s*\([^)]*\)\s*', '', name)  # Remove parenthetical
    name = re.sub(r'[^\w\s]', '', name)  # Remove special chars except spaces
    name = re.sub(r'\s+', ' ', name).strip()  # Normalize spaces
    return name


def find_company_api(company_name: str) -> Optional[Tuple[str, str, str]]:
    """
    Try to find the API URL for a company.
    Returns (api_url, type, matched_name) or None.
    """
    normalized = normalize_company_name(company_name)

    # Direct match
    if normalized in KNOWN_COMPANIES:
        api_url, api_type = KNOWN_COMPANIES[normalized]
        return (api_url, api_type, normalized)

    # Partial match
    for known_name, (api_url, api_type) in KNOWN_COMPANIES.items():
        if known_name in normalized or normalized in known_name:
            return (api_url, api_type, known_name)

    # Word match (any word matches)
    normalized_words = set(normalized.split())
    for known_name, (api_url, api_type) in KNOWN_COMPANIES.items():
        known_words = set(known_name.split())
        if normalized_words & known_words:  # Intersection
            return (api_url, api_type, known_name)

    return None


def load_companies_from_excel(file_path: str) -> List[str]:
    """Load company names from an Excel file."""
    try:
        df = pd.read_excel(file_path)
        # Handle case where first company is column name
        first_company = df.columns[0]
        all_companies = [first_company] + df.iloc[:, 0].dropna().tolist()
        return [str(c).strip() for c in all_companies if str(c).strip()]
    except Exception as e:
        logger.error(f"Error loading companies from {file_path}: {e}")
        return []


def generate_company_configs(companies: List[str]) -> Dict[str, Dict]:
    """Generate config entries for a list of companies."""
    configs = {}
    matched = 0
    unmatched = []

    for company in companies:
        result = find_company_api(company)
        if result:
            api_url, api_type, matched_name = result
            # Create a safe key
            key = re.sub(r'[^\w]', '', company.replace(' ', ''))[:20]
            if key in configs:
                key = f"{key}_{len(configs)}"

            configs[key] = {
                "name": company,
                "api_url": api_url,
                "type": api_type if api_type not in ["google", "amazon", "apple", "meta", "microsoft", "netflix", "tesla", "tiktok"] else None,
            }
            # Remove None type
            if configs[key]["type"] is None:
                del configs[key]["type"]
            matched += 1
        else:
            unmatched.append(company)

    logger.info(f"Matched {matched}/{len(companies)} companies to career APIs")
    if unmatched:
        logger.debug(f"Unmatched companies: {unmatched[:20]}...")

    return configs, unmatched
