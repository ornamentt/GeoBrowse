from requests.cookies import RequestsCookieJar


# Do not commit real browser cookies. If a local workflow needs cookies, load
# them from a private file or environment-specific setup outside this module.
COOKIES_LIST = []

COOKIES = RequestsCookieJar()
