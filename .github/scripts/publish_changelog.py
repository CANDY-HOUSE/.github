#!/usr/bin/env python3
"""Publish changelog.html to the Shopify page jp.candyhouse.co/pages/changelog.

Auth (either one):
  SHOPIFY_ACCESS_TOKEN                        Admin API token of a custom app, or
  SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET   Dev Dashboard app (client credentials grant)
The app needs the write_content (or write_online_store_pages) scope.

Set DRY_RUN=1 to validate the file without calling Shopify.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SHOP = os.environ.get("SHOPIFY_SHOP", "candy-house-japan.myshopify.com")
API_VERSION = os.environ.get("SHOPIFY_API_VERSION", "2026-07")
PAGE_ID = os.environ.get("SHOPIFY_PAGE_ID", "gid://shopify/Page/86556934207")
PAGE_HANDLE = "changelog"
SOURCE = os.environ.get("CHANGELOG_FILE", "changelog.html")

MUTATION = """
mutation PublishChangelog($id: ID!, $page: PageUpdateInput!) {
  pageUpdate(id: $id, page: $page) {
    page { id handle updatedAt }
    userErrors { code field message }
  }
}
"""


def fail(message):
    print(f"::error::{message}")
    sys.exit(1)


def post(url, data, headers):
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        # Never print the response body of the token endpoint; status is enough.
        fail(f"Shopify returned HTTP {error.code} for {url.split('?')[0]}")
    except urllib.error.URLError as error:
        fail(f"Could not reach Shopify: {error.reason}")


def access_token():
    token = os.environ.get("SHOPIFY_ACCESS_TOKEN", "").strip()
    if token:
        return token
    client_id = os.environ.get("SHOPIFY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SHOPIFY_CLIENT_SECRET", "").strip()
    if not (client_id and client_secret):
        fail(
            "No Shopify credentials. Add the repository secret SHOPIFY_ACCESS_TOKEN, "
            "or SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET."
        )
    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode()
    result = post(
        f"https://{SHOP}/admin/oauth/access_token",
        body,
        {"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = result.get("access_token")
    if not token:
        fail("Shopify did not return an access token.")
    print(f"::add-mask::{token}")
    return token


def read_body():
    with open(SOURCE, "rb") as file:
        body = file.read().decode("utf-8")
    # Refuse to overwrite the live page with something that is clearly not the changelog.
    problems = []
    if len(body) < 50_000:
        problems.append(f"only {len(body)} characters")
    for marker in ('<div class="chlog">', 'id="changelog"', "</style>"):
        if marker not in body:
            problems.append(f"missing {marker}")
    if problems:
        fail(f"{SOURCE} does not look like the changelog ({'; '.join(problems)}). Not publishing.")
    return body


def main():
    body = read_body()
    print(f"{SOURCE}: {len(body)} characters")
    if os.environ.get("DRY_RUN"):
        print("DRY_RUN set, not calling Shopify.")
        return

    payload = json.dumps(
        {"query": MUTATION, "variables": {"id": PAGE_ID, "page": {"body": body}}}
    ).encode("utf-8")
    result = post(
        f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json",
        payload,
        {"Content-Type": "application/json", "X-Shopify-Access-Token": access_token()},
    )

    if result.get("errors"):
        fail(f"GraphQL errors: {json.dumps(result['errors'], ensure_ascii=False)}")
    update = (result.get("data") or {}).get("pageUpdate") or {}
    if update.get("userErrors"):
        fail(f"pageUpdate errors: {json.dumps(update['userErrors'], ensure_ascii=False)}")
    page = update.get("page")
    if not page:
        fail("pageUpdate returned no page. Check the page ID and the app's access scopes.")
    if page.get("handle") != PAGE_HANDLE:
        fail(f"Updated page has handle {page.get('handle')!r}, expected {PAGE_HANDLE!r}.")
    print(f"Published to /pages/{page['handle']} at {page['updatedAt']}")


if __name__ == "__main__":
    main()
