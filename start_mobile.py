"""Local HTTPS test server. Install requirements-mobile.txt before running."""
from __future__ import annotations

import argparse
import ipaddress
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID

ROOT = Path(__file__).resolve().parent


def local_addresses():
    addresses = {'127.0.0.1'}
    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        address = info[4][0]
        if not address.startswith('169.254.'):
            addresses.add(address)
    return sorted(addresses)


def certificates(addresses):
    folder = ROOT / '.certs'
    folder.mkdir(exist_ok=True)
    cert_path, key_path = folder / 'server.pem', folder / 'server-key.pem'
    names = [x509.DNSName('localhost')] + [x509.IPAddress(ipaddress.ip_address(a)) for a in addresses]
    if cert_path.exists() and key_path.exists() and (folder / 'sopvision-ca.crt').exists():
        old = x509.load_pem_x509_certificate(cert_path.read_bytes())
        sans = old.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        has_authority = any(isinstance(e.value, x509.AuthorityKeyIdentifier) for e in old.extensions)
        if has_authority and old.not_valid_after_utc > datetime.now(timezone.utc) + timedelta(days=1) and all(n in sans for n in names):
            return cert_path, key_path
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'SOPVision Local Test CA')])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=90))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
          .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
              key_encipherment=False, data_encipherment=False, key_agreement=False,
              key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'SOPVision Local Test')]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=89))
            .add_extension(x509.SubjectAlternativeName(names), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                key_encipherment=True, data_encipherment=False, key_agreement=False,
                key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    (folder / 'sopvision-ca.crt').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                         serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return cert_path, key_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip', help='Extra LAN IP to include in the HTTPS certificate')
    parser.add_argument('--port', type=int, default=8443)
    args = parser.parse_args()
    addresses = local_addresses()
    if args.ip:
        addresses = sorted(set(addresses + [str(ipaddress.ip_address(args.ip))]))
    cert, key = certificates(addresses)
    print('\nPhone and PC must use the same Wi-Fi. Open one of these URLs:')
    for address in addresses:
        print(f'  https://{address}:{args.port}/worker?station=1')
    print('Install and trust .certs/sopvision-ca.crt on the phone first (README).')
    print('Keep server-key.pem private. This launcher does not modify firewall settings.\n')
    print('Mobile HTTPS forwards to the SAME backend as desktop on port 8000.')
    uvicorn.run('mobile_gateway:app', host='0.0.0.0', port=args.port, timeout_graceful_shutdown=5, access_log=False,
                ssl_certfile=str(cert), ssl_keyfile=str(key))
