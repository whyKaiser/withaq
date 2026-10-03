"""Deterministic local policy for the synthetic corpus; not a general-purpose DLP model."""
import hashlib
import re
import unicodedata
from pathlib import Path

import yaml

from .store import DomainError, digest

DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\w)(?:\+966\s?|00966\s?|0)5(?:[ -]?\d){8}(?!\d)")
SECRET = re.compile(r"national[ _-]?id|password|api[ _-]?key|secret[ _-]?token|رقم\s*الهوية|كلمة\s*المرور|مفتاح\s*(?:الواجهة|api)", re.I)
SAUDI_ID = re.compile(r"(?<!\d)[12]\d{9}(?!\d)")
INJECTION = re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions|تجاهل\s+(?:كل\s+)?التعليمات\s+السابقة", re.I)


def sha(payload):
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalized(payload):
    value = unicodedata.normalize("NFKC", payload).translate(DIGITS)
    return "".join(c for c in value if unicodedata.category(c) not in ("Cf", "Mn"))


class Policy:
    def __init__(self, path=None):
        self.path = Path(path or Path(__file__).resolve().parents[2] / "policies/disclosure.yml")

    def load(self):
        policy = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        if not isinstance(policy, dict) or not isinstance(policy.get("version"), int) or policy["version"] < 1:
            raise DomainError("POLICY_INVALID", 503)
        return policy, digest(policy)

    def inspect(self, payload, destination, account, purpose):
        policy, policy_hash = self.load()
        rule = policy.get("destinations", {}).get(destination)
        reason = None
        if not rule or account != rule["account"] or purpose != rule["purpose"]:
            reason = "DESTINATION_ACCOUNT_OR_PURPOSE_DENIED"
        if len(payload.encode("utf-8")) > policy["max_bytes"]:
            reason = "PAYLOAD_TOO_LARGE"
        value = normalized(payload)
        if SECRET.search(value) or SAUDI_ID.search(value):
            reason = "PROHIBITED_FIELD"
        if INJECTION.search(value):
            reason = "UNTRUSTED_INSTRUCTION"
        if reason:
            return {"decision": "BLOCK", "reason": reason, "payload": "", "policy_hash": policy_hash,
                    "policy_version": policy["version"], "approval": False}
        cleaned = payload
        if policy.get("sanitize_contacts"):
            # Normalize before masking so Arabic/Persian digits and invisible separators cannot bypass it.
            cleaned = PHONE.sub("[PHONE REMOVED]", EMAIL.sub("[EMAIL REMOVED]", value))
        changed = cleaned != payload
        # Reinspect exact sanitized bytes using the same rules, without dropping lineage.
        if SECRET.search(normalized(cleaned)) or SAUDI_ID.search(normalized(cleaned)):
            raise DomainError("SANITIZATION_FAILED", 403)
        return {"decision": "SANITIZE" if changed else ("REQUIRE_APPROVAL" if rule["approval"] else "ALLOW"),
                "reason": "CONTACTS_OR_UNICODE_NORMALIZED" if changed else None,
                "payload": cleaned, "policy_hash": policy_hash, "policy_version": policy["version"],
                "approval": rule["approval"]}
