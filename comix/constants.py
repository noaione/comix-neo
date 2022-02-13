import sys
from os.path import expandvars
from pathlib import Path

__version__ = "0.1.0"
if sys.platform == "win32":
    USER_PATH = Path(expandvars("%LOCALAPPDATA%/ComixNeo"))
else:
    USER_PATH = Path(expandvars("$HOME/.comixneo"))

DEVICE_ID = "f245bb5cce9f2e7fb6bb9b6d7dfe85fa"  # DO NOT CHANGE

API_DOWNLOAD_URL = "https://cmx-secure.comixology.com/ios/api/com.iconology.android.Comics/3.9.7/?deviceType=tablet&lang=en&store=US&action=getUserPurchase"  # noqa: E501
API_ISSUE_URL = "https://digital.comixology.com/ios/api/com.iconology.android.Comics/3.9.7/?deviceType=tablet&lang=en&store=US&action=getIssueSummaries"  # noqa: E501
API_LIST_URL = "https://cmx-secure.comixology.com/ios/api/com.iconology.android.Comics/3.9.7/?deviceType=tablet&lang=en&store=US&action=getPurchaseTransactions"  # noqa: E501

API_HEADERS = {
    "User-Agent": "Comics/3.10.17[3.10.17.310418] Google/10",
    "x-client-application": "com.comixology.comics",
}
