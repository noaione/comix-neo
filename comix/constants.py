import sys
from os.path import expandvars
from pathlib import Path

__version__ = "0.1.2"
if sys.platform == "win32":
    USER_PATH = Path(expandvars("%LOCALAPPDATA%/ComixNeo"))
else:
    USER_PATH = Path(expandvars("$HOME/.comixneo"))

API_DOWNLOAD_URL = "https://cmx-secure.comixology.com/ios/api/com.iconology.android.Comics/3.9.7/?deviceType=tablet&lang=en&store=US&action=getUserPurchase"  # noqa: E501
API_ISSUE_URL = "https://digital.comixology.com/ios/api/com.iconology.android.Comics/3.9.7/?deviceType=tablet&lang=en&store=US&action=getIssueSummaries"  # noqa: E501
API_LIST_URL = "https://cmx-secure.comixology.com/ios/api/com.iconology.android.Comics/3.9.7/?deviceType=tablet&lang=en&store=US&action=getPurchaseTransactions"  # noqa: E501

API_MANIFEST_URL = "https://kindle-digital-delivery.amazon.com/delivery/manifest/kindle.ebook/"

API_HEADERS = {
    "User-Agent": "Comics/3.10.17[3.10.17.310418] Google/10",
    "x-client-application": "com.comixology.comics",
}
