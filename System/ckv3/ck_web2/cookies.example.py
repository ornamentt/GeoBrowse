from requests.cookies import RequestsCookieJar


# Copy this file to cookies.py for a private local experiment only.
# Never commit real cookie values.
COOKIES_LIST = [
    # {
    #     "domain": ".example.com",
    #     "name": "session",
    #     "value": "REPLACE_WITH_LOCAL_COOKIE",
    #     "path": "/",
    # },
]

COOKIES = RequestsCookieJar()
for cookie in COOKIES_LIST:
    COOKIES.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie.get("path", "/"))
