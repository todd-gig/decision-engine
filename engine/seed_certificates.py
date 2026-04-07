"""
seed_certificates.py
Seeds initial trust certificates into Firestore.
Run once after firebase deploy.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.trust_certificates import CertificateAuthority, bootstrap_certificates

try:
    import firebase_admin
    from firebase_admin import credentials, firestore as fb_firestore
    HAS_FIREBASE = True
except ImportError:
    HAS_FIREBASE = False


def seed():
    ca = CertificateAuthority()
    certs = bootstrap_certificates(ca)

    print(f"Generated {len(certs)} trust certificates.")

    if not HAS_FIREBASE:
        print("[warn] firebase_admin not installed — printing certificates only.\n")
        for c in certs:
            import json
            print(json.dumps(c.to_dict(), indent=2))
        return

    # Init Firebase
    if not firebase_admin._apps:
        cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if cred_path:
            cred = credentials.Certificate(cred_path)
        else:
            cred = credentials.ApplicationDefault()
        firebase_admin.initialize_app(cred)

    db = fb_firestore.client()
    col = db.collection("trust_certificates")

    for cert in certs:
        doc = cert.to_dict()
        col.document(cert.cert_id).set(doc)
        print(f"  Seeded [{cert.domain}] cert {cert.cert_id[:8]}… trust={int(cert.trust_level)}")

    print("Done.")


if __name__ == "__main__":
    seed()
