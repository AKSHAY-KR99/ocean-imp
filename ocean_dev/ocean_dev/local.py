import base64

DATABASE_NAME = 'ocean'
DATABASE_USER = 'oceanuser'
DATABASE_PASSWORD = 'ocean@123'
DATABASE_HOST = '127.0.0.1'
DATABASE_PORT = '5432'
FRONTEND_URL = 'https://www.testoceanplatform.com/'
BACKEND_URL = 'https://www.testoceanplatform.com/api/v1/ocean/admin'

# # Xero keys and URL's
# SIGNUP_SCOPE = 'offline_access+openid+profile+email+accounting.transactions+' \
#          'accounting.contacts+accounting.settings+' \
#          'accounting.attachments+accounting.reports.read'
# REDIRECT_URI = 'https://b522-2409-4073-2e93-77db-147a-4fab-45a9-e65.ngrok.io'
# # REDIRECT_URI='http://localhost:8001/account/token/'
# CLIENT_ID = '0F28E5B43A7445BCA5DE7B8D2D64A965'
# CLIENT_SECRET = 'iRxAhGllAUITY-ktKLAY5v37s2IT29NeaBvMo00RSpY8DjRh'
STATE = '123'
#

#
AUTH_URL_GENERATOR = 'https://login.xero.com/identity/connect/authorize?response_type=code'
TOKEN_URL = 'https://identity.xero.com/connect/token'
CONNECTION_URL = 'https://api.xero.com/connections'
BALANCE_SHEET_URL = 'https://api.xero.com/api.xro/2.0/Reports/BalanceSheet'
PROFIT_LOSS_URL = 'https://api.xero.com/api.xro/2.0/Reports/ProfitAndLoss'
BANK_SUMMARY_URL = 'https://api.xero.com/api.xro/2.0/Reports/BankSummary'
REFRESHING_URL = 'https://identity.xero.com/connect/token'
USER_DETAILS = 'https://api.xero.com/api.xro/2.0/Users'
CONTACT_DETAILS = 'https://api.xero.com/api.xro/2.0/Contacts'

# CLIENT_ID = "D9B541ECA6E34916AB838BF8E641F8F1"
# CLIENT_SECRET = "phFzovy45PMf0zsEx_Tt7OxoT8Z77Bl45JJbzydz5cGtsn2_"


CLIENT_ID = "12F7583836C942418227E7EAC79D11D6"
CLIENT_SECRET = "l9llhAyLiv0gViFV4R1A-qMs9BD8ANXsYPbNRUmzASkWqtnO"

SIGNUP_SCOPE = "offline_access+openid+profile+email"
SIGN_UP_REDIRECT_URI = "http://localhost:8001/account/xero/callback/"

token_value = CLIENT_ID + ':' + CLIENT_SECRET
BASIC_TOKEN = base64.urlsafe_b64encode(token_value.encode()).decode()

# AWS SNS keys

# AWS_ACCESS_KEY = "AKIAVXLDNFMCUBMJOS24"
# AWS_SECRET_ACCESS_KEY = "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"
# AWS_TOPIC_ARN = "arn:aws:sns:ap-south-1:393734859525:OCEAN-TOPIC"
REGION_NAME = "ap-south-1"
# AWS_TOPIC_ARN = "arn:aws:sns:ap-south-1:393734859525:TEST"
# AWS_TOPIC_ARN = "arn:aws:sns:ap-south-1:393734859525:TEST-OTP"

AWS_ACCESS_KEY = 'AKIAVXLDNFMCR4GVDT3E'
AWS_SECRET_ACCESS_KEY = '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'
AWS_TOPIC_ARN = 'arn:aws:sns:ap-south-1:393734859525:OTPCHECK'

# Codat constants
CODAT_API_KEY = 'NVfJAZiDLd6oZ65LOrKCxp459SBa1s1jb3azmkfd'
CODAT_AUTHORIZATION_KEY = 'Basic TlZmSkFaaURMZDZvWjY1TE9yS0N4cDQ1OVNCYTFzMWpiM2F6bWtmZA=='

AUTH_PROVIDERS = {
    "email": "email", "xero": "xero", "google": "google"
}
# Social Authentication Status
INITIATED = "INITIATED"
UPDATED_DETAILS = "UPDATED_DETAILS"
COMPLETED = "COMPLETED"
COMPLETE_PROFILE = "COMPLETE_PROFILE"