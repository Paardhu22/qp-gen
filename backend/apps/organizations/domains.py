"""Matching a signup email to the school it belongs to.

Signup asks a teacher to find their school in a dropdown of every organization
on the platform. That is a list which only grows, it is sorted alphabetically
rather than by anything the teacher knows, and picking the wrong "St. Mary's"
sends a join request to a school that will never approve it — the teacher is
then stuck in `pending` with nothing to show for it and no obvious way back.

A school's email domain is the fact that already answers this. A teacher
signing up as `r.menon@dpsbangalore.edu.in` belongs to the organization that
claims `dpsbangalore.edu.in`, and the dropdown should say so before they
choose.

This is a *hint*, never an authorisation. A matched domain pre-selects the
school and nothing more: the membership still starts pending and still needs an
admin's approval, because email domains are trivially spoofable at signup and
"@gmail.com" would otherwise adopt half the platform. The one place a domain
does grant something — a teacher invite link — grants it because an admin
issued the link, not because the domain matched.
"""

from __future__ import annotations

from typing import Iterable, List

#: Public mailbox providers. A school may legitimately run on one of these, and
#: some genuinely do — but claiming `gmail.com` as an organization's domain
#: would silently match every consumer address on the platform, so the claim is
#: refused at the point an admin tries to save it.
PUBLIC_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.co.in",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "icloud.com",
        "me.com",
        "aol.com",
        "protonmail.com",
        "proton.me",
        "rediffmail.com",
        "zoho.com",
        "mail.com",
        "yandex.com",
    }
)

MAX_DOMAINS = 10


def domain_of_email(email: str) -> str:
    """`"R.Menon@DPSBangalore.edu.in "` → `"dpsbangalore.edu.in"`."""
    cleaned = (email or "").strip().lower()
    if "@" not in cleaned:
        return ""
    return cleaned.rsplit("@", 1)[1].strip()


def clean_domain(value: str) -> str:
    """Normalise one entry as typed into a settings field.

    Accepts what people actually type — `@school.edu`, `School.EDU`,
    `https://school.edu/`, `www.school.edu` — because rejecting those would
    make the field feel broken rather than strict.
    """
    text = (value or "").strip().lower()
    if not text:
        return ""
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    text = text.split("/", 1)[0]
    text = text.lstrip("@").strip()
    if text.startswith("www."):
        text = text[4:]
    if "@" in text:
        text = text.rsplit("@", 1)[1]
    return text


def domain_list(raw: str | None) -> List[str]:
    """The stored comma-separated string as a de-duplicated list."""
    out: List[str] = []
    for chunk in (raw or "").replace("\n", ",").split(","):
        domain = clean_domain(chunk)
        if domain and domain not in out:
            out.append(domain)
    return out


def normalize_domains(value) -> str:
    """Validate and canonicalise what an admin typed, for storage.

    Raises `ValueError` with a sentence a school administrator can act on —
    these surface directly in a toast.
    """
    if isinstance(value, (list, tuple)):
        value = ",".join(str(v) for v in value)
    domains = domain_list(value)

    if len(domains) > MAX_DOMAINS:
        raise ValueError(
            f"That is more than {MAX_DOMAINS} domains. List only the ones your staff actually use."
        )
    for domain in domains:
        if domain in PUBLIC_EMAIL_DOMAINS:
            raise ValueError(
                f"'{domain}' is a public email provider, so it cannot identify your school. "
                "Use the domain your staff addresses end in."
            )
        if "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError(f"'{domain}' does not look like an email domain.")
        if any(ch.isspace() for ch in domain):
            raise ValueError(f"'{domain}' does not look like an email domain.")
    return ",".join(domains)


def matches(organization, email: str) -> bool:
    """True when `email`'s domain is one this organization claims."""
    domain = domain_of_email(email)
    if not domain:
        return False
    return domain in domain_list(getattr(organization, "email_domains", ""))


def organizations_matching(organizations: Iterable, email: str) -> List:
    domain = domain_of_email(email)
    if not domain:
        return []
    return [
        org for org in organizations if domain in domain_list(getattr(org, "email_domains", ""))
    ]
