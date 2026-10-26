import pytest

from app.github.urls import InvalidRepoUrl, RepoRef, parse_repo_url

URL_TEST_CASES = [
    # (input_url, expected_owner, expected_name, expected_ref)
    ("https://github.com/facebook/react", "facebook", "react", None),
    ("http://github.com/facebook/react", "facebook", "react", None),
    ("www.github.com/facebook/react", "facebook", "react", None),
    ("github.com/facebook/react", "facebook", "react", None),
    ("facebook/react", "facebook", "react", None),
    ("https://github.com/facebook/react.git", "facebook", "react", None),
    ("https://github.com/facebook/react/", "facebook", "react", None),
    ("https://github.com/facebook/react/tree/main", "facebook", "react", "main"),
    ("https://github.com/facebook/react/tree/main/packages/react", "facebook", "react", "main"),
    ("https://github.com/facebook/react/blob/v18.2.0/package.json", "facebook", "react", "v18.2.0"),
    ("https://github.com/facebook/react/issues/123", "facebook", "react", None),
    ("https://github.com/facebook/react/pull/456", "facebook", "react", None),
    ("vercel/next.js", "vercel", "next.js", None),
    ("https://github.com/tailwindlabs/tailwindcss.git/", "tailwindlabs", "tailwindcss", None),
    (
        "https://www.github.com/owner-with-dash/repo.with.dots",
        "owner-with-dash",
        "repo.with.dots",
        None,
    ),
]

HOSTILE_URL_CASES = [
    "https://evil.com/facebook/react",
    "https://gitlab.com/facebook/react",
    "https://githụb.com/facebook/react",  # Unicode lookalike
    "https://github.com/evil/repo/unknown/extra/path",  # Unsupported path segment
    "https://github.com/",
    "https://github.com/only-owner",
    "facebook/",
    "/react",
    "../evil/repo",
    "",
    "   ",
    "not a url",
    "https://github.com/owner/../evil",
    "https://github.com/owner/with spaces/in/name",
    "https://github.com/owner/" + "a" * 150,  # Exceeds max length
]


@pytest.mark.parametrize("url,expected_owner,expected_name,expected_ref", URL_TEST_CASES)
def test_valid_repo_urls(url, expected_owner, expected_name, expected_ref):
    ref = parse_repo_url(url)
    assert isinstance(ref, RepoRef)
    assert ref.owner == expected_owner
    assert ref.name == expected_name
    assert ref.ref == expected_ref


@pytest.mark.parametrize("hostile_url", HOSTILE_URL_CASES)
def test_hostile_and_invalid_repo_urls(hostile_url):
    with pytest.raises(InvalidRepoUrl):
        parse_repo_url(hostile_url)
